from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from recipes.demo_store import DemoBank
from recipes.workflow_api import load_reference_catalog
from recipes.recorded_eligibility import evaluate, binding, VERSION
from backend.tests.recorded_tracking_fixtures import with_tracking

BUNDLE=json.loads((Path(__file__).parents[1]/'recipe_trial_assets/reviewed_trial.json').read_text())
OBS=json.loads((Path(__file__).parent/'fixtures/two_fill_observations.json').read_text())['observations']
CATALOG,_=load_reference_catalog()


def observation(label='Video 1 · Vial 6'):
    return with_tracking(next(o for o in OBS if o['label']==label))


def recovery(o):
    o=deepcopy(o);frames=o['recorded_geometry']['frames'];i=8;identity=frames[i]['detections'][0]['track_id']
    t=frames[i]['captured_at'];end=frames[i+2]['captured_at']
    frames[i]['detections']=[];frames[i]['issues']=['NO_SUPPORTED_VIAL_GEOMETRY']
    frames[i]['identity_events']=[{'event':'DETECTION_LOSS_PENDING','track_id':identity,'captured_at':t}]
    frames[i+1]['detections'][0].update(status='CONFIRMING',track_id=None)
    frames[i+2]['identity_events']=[{'event':'DETECTION_LOSS_REASSOCIATED','track_id':identity,
        'gap_started_at':t,'last_missing_at':t,'recovered_at':end,'interrupted_samples':1,'duration_seconds':end-t}]
    return o


class EligibilityTests(unittest.TestCase):
    def test_supported_without_surface_or_strict_every_frame_requirement(self):
        o=observation();self.assertEqual(evaluate(o)['status'],'SUPPORTED')
        recovered=recovery(o);r=evaluate(recovered)
        self.assertEqual(r['status'],'SUPPORTED_WITH_RECOVERY');self.assertFalse(r['numeric_surface_used'])
        self.assertEqual(len(r['supported_recoveries']),1)
    def test_missing_empty_or_unversioned_evidence_is_held(self):
        for report in (None,{}, {'status':'SUPPORTED'}):
            o=observation();o['recorded_geometry']=report
            self.assertEqual(evaluate(o)['status'],'HELD')
        archived=deepcopy(OBS[0]);self.assertIsNone(evaluate(archived))
    def test_provenance_revision_binding_and_surface_tampering_are_held(self):
        mutations=[('source_sha256','f'*64),('tracker_sha256','b'*64),('policy_version','unknown'),
                   ('observation_sha256','0'*64),('numeric_surface_used',True)]
        for key,value in mutations:
            with self.subTest(key=key):
                o=observation();o['recorded_geometry'][key]=value;self.assertEqual(evaluate(o)['status'],'HELD')
        o=observation();o['raw_rgb']['nominal']=[1,1,1]
        self.assertIn('TRACKING_OBSERVATION_BINDING_MISMATCH',evaluate(o)['hold_reasons'])
    def test_fragmented_ids_input_gaps_and_resets_block(self):
        for kind in ('identity','gap','reset'):
            o=observation();frames=o['recorded_geometry']['frames'];i=8
            if kind=='identity':frames[i]['detections'][0]['track_id']='a different vial'
            elif kind=='gap':del frames[i:i+2]
            else:frames[i]['identity_events']=[{'event':'DETECTION_LOSS_IDENTITY_RESET','reason':'BUDGET_EXPIRED'}]
            self.assertEqual(evaluate(o)['status'],'HELD',kind)
    def test_unresolved_or_falsely_claimed_recovery_blocks(self):
        for kind in ('no-event','over-budget','wrong-id','wrong-count'):
            o=recovery(observation());report=o['recorded_geometry'];event=report['frames'][10]['identity_events'][0]
            if kind=='no-event':report['frames'][10]['identity_events']=[]
            elif kind=='over-budget':event['duration_seconds']=3
            elif kind=='wrong-id':event['track_id']='other'
            else:event['interrupted_samples']=7
            self.assertEqual(evaluate(o)['status'],'HELD',kind)
    def test_final_colour_is_direct_source_bound_and_visible(self):
        for kind in ('missing-box','outside-roi','wrong-sha','wrong-time','wrong-dimensions'):
            o=observation();check=o['recorded_geometry']['colour_checks'][0]
            if kind=='missing-box':check['box']=None
            elif kind=='outside-roi':check['box']['x']=.7
            elif kind=='wrong-sha':check['sha256']='c'*64
            elif kind=='wrong-time':check['actual_seconds']+=.1
            else:check['dimensions']=[320,240]
            self.assertEqual(evaluate(o)['status'],'HELD',kind)
    def test_no_preflow_or_no_postcolour_confirmation_blocks(self):
        for phase in ('before','after'):
            o=observation();frames=o['recorded_geometry']['frames']
            if phase=='before':o['recorded_geometry']['frames']=[f for f in frames if f['captured_at']>o['source_episode_intervals'][0]['start'][0]]
            else:o['recorded_geometry']['frames']=[f for f in frames if f['captured_at']<max(o['sample_actual_seconds'])]
            self.assertEqual(evaluate(o)['status'],'HELD',phase)


class GuardedBankTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.bank=self.open();self.addCleanup(self.bank.close)
    def open(self,path=None):
        return DemoBank(path or self.root/'bank.sqlite3',BUNDLE['profiles'],BUNDLE['rules'],{int(i) for i in CATALOG['recipes']},
            normal_paths=[self.root/'normal.sqlite3'],bundle_revision='geometry-gate-tests',allow_development_writes=True)
    def test_missing_tracking_cannot_create_any_pattern(self):
        o=observation();o.pop('recorded_geometry');r=self.bank.assess(o)['assessment']
        self.assertEqual(r['action'],'UNRESOLVED');self.assertIn('TRACKING_EVIDENCE_MISSING',r['hold_reasons'])
        self.assertIsNone(r['recipe_id']);self.assertEqual(self.bank.counts()['discovered_patterns'],0)
    def test_geometry_hold_blocks_reference_and_discovered_reuse(self):
        self.bank.assess(observation())
        for label in ('Video 1 · Vial 6','Video 2 · Vial 1'):
            o=observation(label);o['observation_id']+='held';o=with_tracking(o)
            o['recorded_geometry']['colour_checks'][0]['box']=None
            result=self.bank.assess(o)['assessment'];self.assertEqual(result['action'],'UNRESOLVED');self.assertIsNone(result['recipe_id'])
        self.assertEqual(self.bank.counts()['linked_occurrences'],1)
    def test_held_fill_cannot_vote_and_qualified_recovery_can_confirm(self):
        self.bank.assess_many([observation('Video 1 · Vial 6'),observation('Video 1 · Vial 16')])
        a=self.bank.assess(observation('Video 1 · Vial 13'))['assessment']
        self.assertEqual(a['pattern_membership']['qualifying_fill_count'],1)
        bad=observation('Video 2 · Vial 3');bad['recorded_geometry']['colour_checks'][0]['box']=None
        self.bank.assess(bad);self.assertEqual(self.bank.pending_patterns()[0]['qualifying_fill_count'],1)
        good=deepcopy(next(o for o in OBS if o['label']=='Video 2 · Vial 3'));good['observation_id']+='qualified-revision';good=recovery(with_tracking(good))
        result=self.bank.assess(good)['assessment']
        self.assertEqual(result['pattern_membership']['recipe_id'],102)
        self.assertEqual(result['recorded_tracking']['status'],'SUPPORTED_WITH_RECOVERY')
        self.assertEqual(result['color']['status'],'CONFLICTING')
        repeat=self.bank.assess(good);self.assertTrue(repeat['idempotent_replay'])
        self.assertEqual(self.bank.pending_patterns()[0]['qualifying_fill_count'],2)
        # Also exercise the confirmed-pattern fast reuse path with no baseline
        # timing reference; a geometry hold must still block the third vote.
        self.bank.references=[]
        third=deepcopy(good);third.pop('recorded_geometry');third['observation_id']='third-held';third['source_lineage']['video_sha256']='b'*64
        third=with_tracking(third);third['recorded_geometry']['colour_checks'][0]['box']=None
        blocked=self.bank.assess(third)['assessment'];self.assertIsNone(blocked.get('pattern_membership'))
        self.assertIsNone(blocked['recipe_id']);self.assertEqual(self.bank.pending_patterns()[0]['qualifying_fill_count'],2)
    def test_identity_reuse_between_distinct_fills_is_held_before_batch_writes(self):
        a=observation('Video 1 · Vial 6');b=observation('Video 1 · Vial 16')
        identity=a['recorded_geometry']['frames'][0]['detections'][0]['track_id']
        b=with_tracking(b,identity=identity)
        result=self.bank.assess_many([a,b])
        self.assertTrue(all(r['assessment']['recorded_tracking']['status']=='HELD' for r in result['results']))
        self.assertEqual(self.bank.counts()['discovered_patterns'],0)
        self.assertEqual(self.bank.counts()['linked_occurrences'],0)
    def test_identity_reuse_in_later_transaction_is_held(self):
        a=observation();self.bank.assess(a)
        b=with_tracking(next(o for o in OBS if o['label']=='Video 1 · Vial 16'),identity=a['recorded_geometry']['frames'][0]['detections'][0]['track_id'])
        result=self.bank.assess(b)['assessment']
        self.assertIn('TRACKING_ID_REUSED_ACROSS_FILLS',result['hold_reasons']);self.assertIsNone(result['recipe_id'])
    def test_missing_surface_does_not_block_matching_and_restart_is_immutable(self):
        o=observation();saved=self.bank.assess(o)['assessment'];raw=self.bank.connection.execute('SELECT result FROM demo_assessments').fetchone()[0]
        reopened=self.open();self.addCleanup(reopened.close)
        replay=reopened.assess(o)['assessment'];self.assertEqual(saved,replay)
        self.assertEqual(reopened.connection.execute('SELECT result FROM demo_assessments').fetchone()[0],raw)
        self.assertEqual(replay['recipe_id'],100)
    def test_version_13_store_is_preserved_and_requires_separate_version_14_file(self):
        path=self.root/'old.sqlite3'
        with patch('recipes.demo_store.ENGINE_VERSION','recorded-pattern-demo/1.3'):
            old=self.open(path);old.assess(deepcopy(OBS[5]));before=old.connection.execute('SELECT result FROM demo_assessments').fetchall();old.close()
        with self.assertRaises(ValueError):self.open(path)
        import sqlite3
        c=sqlite3.connect(path);self.assertEqual(c.execute('SELECT result FROM demo_assessments').fetchall(),before);c.close()
