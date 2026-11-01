from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from app import create_app
from recipes.recorded_producer import RecordedVideoProducer, NativeDecoder, measure_triplet
from recipes.observation.features import extract
from backend.tests.recorded_tracking_fixtures import with_tracking

PREFIX='/api/recipe-workflow/demo/producer'
TOKEN={'Authorization':'Bearer producer-test'}

class ProducerTests(unittest.TestCase):
    def setUp(self):
        env=patch.dict(os.environ,{'INFERENCE_TOKEN':'producer-test'});env.start();self.addCleanup(env.stop)
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.app=create_app({}, {'TESTING':True,'RECIPE_DB_PATH':str(self.root/'normal.sqlite3'),
            'TRACKER_SCHEDULER_ENABLED':False,'RECIPE_DEMO_ENABLED':True,
            'RECIPE_DEMO_DB_PATH':str(self.root/'demo.sqlite3'),'RECORDED_VIDEO_ROOT':self.root})
        self.client=self.app.test_client();self.producer=self.app.extensions['recorded_video_producer']
        self.addCleanup(self.close)
        (self.root/'vial_fill_video_1.mp4').write_bytes(b'synthetic fixture only')
        bundle=json.loads((Path(__file__).parents[1]/'recipe_demo_assets/recorded_observations.json').read_text())
        self.observation=deepcopy(next(o for o in bundle['observations'] if o['vial_id']=='V1-V06'))
        self.observation['observation_id']='fresh-unit-fixture'
        self.observation=with_tracking(self.observation)

    def close(self):
        self.producer.close();self.app.extensions['recipe_demo_service'].bank.close()
        self.app.extensions['recipe_store'].close();self.app.extensions['tracker_manager'].shutdown()

    def result(self):return {'observations':[deepcopy(self.observation)],'held_visits':[],'detected_fill_count':1}
    def post(self,body=None,path='/videos/video-1',headers=TOKEN):
        return self.client.post(PREFIX+path,json={} if body is None else body,headers=headers)
    def wait(self):
        # A queue barrier waits for the one bounded worker, without polling sleeps.
        self.producer.executor.submit(lambda:None).result(timeout=10)

    def test_fresh_job_saved_and_reprocessing_is_idempotent(self):
        self.producer.runner=lambda *args:self.result()
        with patch.object(NativeDecoder,'capability',return_value={'available':True,'decoder':'fixture','reason':None}):
            self.assertEqual(self.post().status_code,202);self.wait()
            result=self.client.get(PREFIX+'/videos/video-1',headers=TOKEN).get_json()
            self.assertEqual(result['state'],'completed');self.assertEqual(len(result['assessments']),1)
            self.assertEqual(result['assessments'][0]['recipe_id'],100)
            self.assertEqual(self.post().status_code,202);self.wait()
        self.assertEqual(self.producer.bank.counts(),{'discovered_patterns':1,'saved_assessments':1,'linked_occurrences':1})
        self.assertEqual(self.producer.get('video-1')['replayed_assessments'],1)
        self.assertEqual(self.app.extensions['recipe_store'].recipes.list_recipes('UNMATCHED'),())
        self.assertEqual(self.app.extensions['recipe_store'].recipes.list_recipes('INTENDED'),())

    def test_duplicate_start_shares_active_job(self):
        started=Event();release=Event()
        def runner(*args):started.set();release.wait(timeout=5);return self.result()
        self.producer.runner=runner
        try:
            with patch.object(NativeDecoder,'capability',return_value={'available':True,'reason':None}):
                self.post();self.assertTrue(started.wait(timeout=2))
                self.assertEqual(self.post().status_code,202)
                (self.root/'vial_fill_video_2.mp4').write_bytes(b'fixture')
                self.assertEqual(self.post(path='/videos/video-2').status_code,409)
        finally:release.set();self.wait()
        self.assertEqual(self.producer.bank.counts()['saved_assessments'],1)

    def test_failed_observation_batch_rolls_back_all_recipe_writes(self):
        result=self.result();result['observations'].append({'observation_id':'invalid'})
        self.producer.runner=lambda *args:result
        with patch.object(NativeDecoder,'capability',return_value={'available':True,'reason':None}),self.assertLogs(level='ERROR'):
            self.post();self.wait()
        self.assertEqual(self.producer.get('video-1')['state'],'failed')
        self.assertEqual(self.producer.bank.counts()['saved_assessments'],0)
        self.assertEqual(self.producer.bank.counts()['discovered_patterns'],0)

    def test_geometry_publish_failure_prevents_recipe_writes(self):
        from recipes.geometry_tracking import VERSION
        result=self.result();result.update(geometry_frames=[{'version':VERSION}],source_sha256=self.observation['source_lineage']['video_sha256'])
        self.producer.runner=lambda *args:result
        with patch.object(self.app.extensions['geometry_service'],'publish',side_effect=OSError('fixture cache fault')),patch.object(NativeDecoder,'capability',return_value={'available':True,'reason':None}),self.assertLogs(level='ERROR'):
            self.post();self.wait()
        self.assertEqual(self.producer.get('video-1')['state'],'failed')
        self.assertEqual(self.producer.bank.counts()['saved_assessments'],0)
        self.assertEqual(self.producer.bank.counts()['discovered_patterns'],0)

    def test_decode_failure_never_opens_assessment_transaction(self):
        def fail(*args):raise ValueError('synthetic decoder fault')
        self.producer.runner=fail
        with patch.object(NativeDecoder,'capability',return_value={'available':True,'reason':None}),self.assertLogs(level='ERROR'):
            self.post();self.wait()
        self.assertEqual(self.producer.get('video-1')['state'],'failed')
        self.assertEqual(self.producer.get('video-1')['assessments'],[])

    def test_auth_source_and_body_constraints(self):
        self.assertEqual(self.post(headers={}).status_code,401)
        self.assertEqual(self.post({'path':'/tmp/other.mp4'}).status_code,400)
        self.assertEqual(self.post(path='/videos/video-99').status_code,404)
        self.assertEqual(self.post(path='/videos/video-2').status_code,404)
        self.assertEqual(self.client.post(PREFIX+'/videos/video-1',json={},headers={**TOKEN,'Origin':'https://untrusted.example'}).status_code,403)

    def test_unavailable_decoder_is_an_explicit_service_error(self):
        with patch.object(NativeDecoder,'capability',return_value={'available':False,'reason':'Decoder unavailable'}):
            r=self.post();self.assertEqual(r.status_code,503);self.assertIn('Decoder unavailable',r.get_json()['error'])
        self.assertEqual(self.producer.get('video-1')['state'],'idle')

    def test_saved_results_survive_producer_restart(self):
        self.producer.bank.assess(self.observation)
        other=RecordedVideoProducer(self.producer.bank,self.root)
        try:
            result=other.get('video-1');self.assertEqual(result['state'],'saved');self.assertEqual(len(result['assessments']),1)
        finally:other.close()

    def test_status_does_not_start_decoding(self):
        r=self.client.get(PREFIX+'/status',headers=TOKEN);self.assertEqual(r.status_code,200)
        self.assertEqual(r.get_json()['input_mode'],'FRESH_RECORDED_VIDEO_OBSERVATION')
        self.assertEqual(self.producer.jobs,{})

class AcquisitionChecks(unittest.TestCase):
    def test_geometry_rejected_before_feature_extraction(self):
        with self.assertRaises(ValueError):extract(np.zeros((481,640,3),dtype=np.uint8))

    def test_spatial_trace_uses_stream_pixels(self):
        a=np.full((480,640,3),128,dtype=np.uint8);a[100:140,304:310]=[20,80,210]
        f,_=extract(a);self.assertEqual(f['trace_contrast_bins'].shape,(20,22,3))
        self.assertGreater(np.linalg.norm(f['trace_contrast_bins'][:,8:14]),100)

    def test_temporal_color_instability_is_retained(self):
        with TemporaryDirectory() as tmp:
            paths=[]
            for i,color in enumerate(((80,90,100),(80,90,100),(110,90,100))):
                path=Path(tmp)/f'{i}.png';Image.new('RGB',(640,480),color).save(path);paths.append(path)
            raw,frames=measure_triplet(paths)
        self.assertGreater(raw['temporal_distance'],2.24);self.assertEqual(len(frames),3)

if __name__=='__main__':unittest.main()
