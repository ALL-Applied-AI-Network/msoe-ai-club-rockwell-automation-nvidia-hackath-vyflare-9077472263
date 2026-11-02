import io
import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from recipes.recording_sources import RecordingSources, MAX_UPLOAD
from recipes.inspection_log import completion_time, observation_events, playback_events
import test_recorded_producer as fixtures
PREFIX,TOKEN=fixtures.PREFIX,fixtures.TOKEN

class SourceTests(unittest.TestCase):
    def test_new_recording_is_content_addressed_persistent_and_deduplicated(self):
        with TemporaryDirectory() as t:
            root=Path(t);sources=RecordingSources(root/'installed',root/'uploads')
            a=sources.register(io.BytesIO(b'new footage'),'video/mp4','../../secret.mp4')
            b=sources.register(io.BytesIO(b'new footage'),'video/mp4','renamed.mp4')
            self.assertEqual(a['video_id'],b['video_id']);self.assertEqual(a['name'],'secret.mp4')
            restored=RecordingSources(root/'installed',root/'uploads')
            self.assertEqual(restored.source(a['video_id']).read_bytes(),b'new footage')
            with self.assertRaises(KeyError):restored.source('../../secret.mp4')
            self.assertEqual(len(list((root/'uploads').glob('*.mp4'))),1)

    def test_opening_copy_of_installed_video_three_reuses_its_identity(self):
        with TemporaryDirectory() as t:
            root=Path(t);(root/'vial_fill_video_3.mp4').write_bytes(b'video three')
            sources=RecordingSources(root,root/'uploads')
            result=sources.register(io.BytesIO(b'video three'),'video/mp4','a new name.mp4')
            self.assertEqual(result['video_id'],'video-3')
            self.assertEqual(list((root/'uploads').iterdir()),[])

    def test_rejects_empty_unsupported_and_oversized_uploads_without_leftovers(self):
        with TemporaryDirectory() as t:
            root=Path(t);s=RecordingSources(root,root/'uploads')
            for data,kind in [(b'', 'video/mp4'),(b'x','application/json')]:
                with self.assertRaises(ValueError):s.register(io.BytesIO(data),kind,'x')
            with patch('recipes.recording_sources.MAX_UPLOAD',2),self.assertRaises(OverflowError):s.register(io.BytesIO(b'abc'),'video/mp4','x')
            self.assertEqual(list((root/'uploads').iterdir()),[])

class AutomaticAPITests(unittest.TestCase):
    setUp=fixtures.ProducerTests.setUp
    close=fixtures.ProducerTests.close
    result=fixtures.ProducerTests.result
    post=fixtures.ProducerTests.post
    wait=fixtures.ProducerTests.wait
    def test_ensure_is_idempotent_and_replay_never_runs_observer_again(self):
        calls=[]
        def runner(*args):calls.append(1);return self.result()
        self.producer.runner=runner
        with patch.object(self.producer,'capability',return_value={'available':True,'reason':None}):
            r=self.post(path='/videos/video-1/ensure');self.assertEqual(r.status_code,202);self.wait()
            r=self.post(path='/videos/video-1/ensure');self.assertEqual(r.status_code,202);self.wait()
        self.assertEqual(len(calls),1);self.assertEqual(self.producer.bank.counts()['saved_assessments'],1)
        job=self.producer.get('video-1');self.assertTrue(job['events'])
        journal=self.producer._journal('video-1');self.assertTrue(journal.exists())
        self.producer.jobs.clear();self.assertEqual(self.producer.get('video-1')['events'],job['events'])

    def test_upload_auth_and_processing_use_registered_source_not_browser_measurements(self):
        with patch.object(self.producer,'capability',return_value={'available':True,'reason':None}):
            self.assertEqual(self.client.post(PREFIX+'/recordings',data=b'new',content_type='video/mp4').status_code,401)
            r=self.client.post(PREFIX+'/recordings',data=b'new recording',content_type='video/mp4',headers={**TOKEN,'X-Recording-Name':'new.mp4'})
        self.assertEqual(r.status_code,201);key=r.get_json()['video_id']
        self.assertEqual(self.producer.source(key).read_bytes(),b'new recording')
        self.assertEqual(self.post(path='/videos/'+key+'/ensure',body={'duration':12}).status_code,400)

    def test_recipe_result_time_cannot_precede_final_samples_or_departure(self):
        a={'observation':self.observation,'observation_id':self.observation['observation_id'],'hold_reasons':[],
           'action':'CREATE_DISCOVERED_PATTERN','recipe_id':100,'timing':{'possible_recipe_ids':[]},'color':{'status':'NOT_EVALUATED'}}
        events=observation_events(a);outcome=next(e for e in events if e['kind']=='recipe')
        self.assertEqual(outcome['at'],completion_time(self.observation))
        self.assertGreaterEqual(outcome['at'],max(self.observation['sample_actual_seconds']))
        later=completion_time(self.observation)+60
        logs=playback_events([{'assessment':a,'initial':True,'at':later,'sequence':0}])
        self.assertEqual(next(e for e in logs if e['kind']=='recipe')['at'],later)

    def test_log_preparation_failure_rolls_back_recipe_changes(self):
        self.producer.runner=lambda *args:self.result()
        with patch.object(self.producer,'capability',return_value={'available':True,'reason':None}),patch.object(Path,'write_text',side_effect=OSError('disk full')),self.assertLogs(level='ERROR'):
            self.post(path='/videos/video-1/ensure');self.wait()
        self.assertEqual(self.producer.get('video-1')['state'],'failed')
        self.assertEqual(self.producer.bank.counts()['saved_assessments'],0)

    def test_replacing_installed_source_does_not_display_old_analysis(self):
        self.producer.runner=lambda *args:self.result()
        with patch.object(self.producer,'capability',return_value={'available':True,'reason':None}):
            self.post(path='/videos/video-1/ensure');self.wait()
        (self.root/'vial_fill_video_1.mp4').write_bytes(b'a different recording')
        value=self.producer.get('video-1')
        self.assertEqual(value['state'],'idle');self.assertEqual(value['events'],[]);self.assertEqual(value['assessments'],[])

    def test_automatic_ensure_queues_another_source_without_manual_retry(self):
        from threading import Event
        from recipes.recorded_producer import file_sha
        from recorded_tracking_fixtures import with_tracking
        entered=Event();release=Event();order=[]
        (self.root/'vial_fill_video_2.mp4').write_bytes(b'second recording')
        def runner(path,source,*args):
            order.append(source)
            if source=='video-1':entered.set();release.wait(timeout=5)
            result=self.result()
            if source=='video-2':
                o=result['observations'][0];o['video_id']=source;o['observation_id']='second-fixture';o['source_lineage']['video_sha256']=file_sha(path)
                result['observations']=[with_tracking(o)]
            return result
        self.producer.runner=runner
        try:
            with patch.object(self.producer,'capability',return_value={'available':True,'reason':None}):
                self.post(path='/videos/video-1/ensure');self.assertTrue(entered.wait(timeout=2))
                queued=self.post(path='/videos/video-2/ensure');self.assertEqual(queued.status_code,202);self.assertEqual(queued.get_json()['state'],'queued')
        finally:release.set();self.wait()
        self.assertEqual(order,['video-1','video-2']);self.assertEqual(self.producer.get('video-2')['state'],'completed')

    def test_a_journal_from_different_bank_state_is_not_displayed(self):
        self.producer.runner=lambda *args:self.result()
        with patch.object(self.producer,'capability',return_value={'available':True,'reason':None}):
            self.post(path='/videos/video-1/ensure');self.wait()
        p=self.producer._journal('video-1');value=json.loads(p.read_text());value['bank_fingerprint']='wrong-bank-state'
        value['events'][0]['title']='Forged Recipe 999';p.write_text(json.dumps(value));self.producer.jobs.clear()
        restored=self.producer.get('video-1')
        self.assertNotIn('Forged Recipe 999',json.dumps(restored['events']))

    def test_legacy_unresolved_log_is_clarified_without_reprocessing_or_bank_writes(self):
        self.observation['hold_reasons']=['ARRIVAL_LEFT_CENSORED']
        self.observation['available_demo_checks_pass']=False
        self.producer.runner=lambda *args:self.result()
        with patch.object(self.producer,'capability',return_value={'available':True,'reason':None}):
            self.post(path='/videos/video-1/ensure');self.wait()
        p=self.producer._journal('video-1');value=json.loads(p.read_text())
        e=next(e for e in value['events'] if e['kind']=='recipe')
        e['title']='Unresolved';e['detail']='Flags: arrival left censored, available demo checks not passed'
        p.write_text(json.dumps(value));before=p.read_bytes()
        assessments=deepcopy(self.producer.bank.baseline_assessments());counts=self.producer.bank.counts()
        self.producer.jobs.clear()
        with patch.object(self.producer,'runner',side_effect=AssertionError('Do not process again')):
            result=self.producer.ensure('video-1')
        restored=next(e for e in result['events'] if e['kind']=='recipe')
        self.assertIn('its arrival was not observed',restored['detail'])
        self.assertEqual((restored['id'],restored['at']),(e['id'],e['at']))
        self.assertEqual(p.read_bytes(),before)
        self.assertEqual(self.producer.bank.baseline_assessments(),assessments)
        self.assertEqual(self.producer.bank.counts(),counts)
