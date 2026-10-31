import copy
import hashlib
import io
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from cosmos_companion import observation,combine_with_model4,validate_context
try:
    from serve_cosmos_companion import create_app,WorkerError
except ModuleNotFoundError as error:
    if error.name!='flask':raise
    create_app=None

DATA=b'diagnostic-video'
CONTEXT=dict(run_id='run-1',vial_id='vial-1',batch_id='batch-1',camera_id='fill-camera',
             timebase_id='video-1',stage='filling',clip_start_s=10,binding_verified=True)

def result():
    return dict(run_id='worker-1',created_at='2026-10-30T12:00:00+00:00',media_kind='video',
        media_sha256=hashlib.sha256(DATA).hexdigest(),model={'adapter':'version-1','base_snapshot':'source'},
        media_info=dict(duration_seconds=20,sampled_frames=32,source_fps=30),seconds=5,prompt='unchanged appearance prompt',
        outputs=dict(adapter=dict(parsed={'observed_color_sequence':['blue','green']},
                                  raw_text='{"observed_color_sequence":["blue","green"]}',valid_color_json=True)))

def amy():
    return dict(vial_id='vial-1',batch_id='batch-1',mode='real',result=dict(
        checkpoint={'estimated_proportions':{'T100':.5,'T200':.2,'T400':.3}},
        review=dict(required=True,automatic_release=False,expected_transition_contamination=True)))

class ContractTests(unittest.TestCase):
    def test_bound_evidence_has_no_invented_measurements(self):
        original=result();context=copy.deepcopy(CONTEXT)
        record=observation(original,context,hashlib.sha256(DATA).hexdigest())
        self.assertEqual(record['appearance']['observed_color_sequence'],['blue','green'])
        self.assertEqual(record['evidence_window']['end_s'],30)
        self.assertIsNone(record['appearance']['transition_timestamps_s'])
        self.assertTrue(all(x is None for x in record['measurements'].values()))
        self.assertEqual(context,CONTEXT)

    def test_invalid_photo_schema_not_repaired(self):
        worker=result();worker['outputs']['adapter']['parsed']={'observed_color_sequence':'green'}
        record=observation(worker,CONTEXT,hashlib.sha256(DATA).hexdigest())
        self.assertEqual(record['status'],'unusable_output')
        self.assertIsNone(record['appearance']['final_visible_color'])

    def test_hash_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError,'hash'):observation(result(),CONTEXT,'different')

    def test_recipe_context_and_nonfinite_offset_rejected(self):
        context=dict(CONTEXT,expected_recipe='water')
        with self.assertRaises(ValueError):validate_context(context)
        for value in (float('nan'),float('inf'),True,-1):
            with self.assertRaises(ValueError):validate_context(dict(CONTEXT,clip_start_s=value))

    def test_missing_binding_does_not_become_tracking(self):
        record=observation(result(),dict(CONTEXT,binding_verified=False),hashlib.sha256(DATA).hexdigest())
        self.assertEqual(record['status'],'unbound')
        with self.assertRaises(ValueError):combine_with_model4(record,amy())

    def test_model4_review_and_estimate_preserved_without_fusion(self):
        record=observation(result(),CONTEXT,hashlib.sha256(DATA).hexdigest());other=amy()
        combined=combine_with_model4(record,other)
        self.assertEqual(combined['model4_response'],other)
        self.assertTrue(combined['model4_response']['result']['review']['expected_transition_contamination'])
        self.assertIsNone(combined['combined_verdict'])
        self.assertFalse(combined['recipe_learning_performed'])
        combined['model4_response']['result']['review']['required']=False
        self.assertTrue(other['result']['review']['required'])

    def test_cross_vial_and_batch_evidence_rejected(self):
        record=observation(result(),CONTEXT,hashlib.sha256(DATA).hexdigest())
        for field in ('vial_id','batch_id'):
            other=amy();other[field]='different'
            with self.assertRaises(ValueError):combine_with_model4(record,other)

class FakeClient:
    def health(self):return dict(ready=True,busy=False,model={'adapter':'version-1'})
    def predict(self,data,suffix):
        self.last=(data,suffix)
        return result()

@unittest.skipIf(create_app is None,'Flask required for companion HTTP tests')
class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.worker=FakeClient();self.app=create_app(self.worker);self.client=self.app.test_client()

    def submit(self,context=None):
        return self.client.post('/v1/cosmos/observe',data={'context':json.dumps(context or CONTEXT),
            'media':(io.BytesIO(DATA),'recipe-labelled-file.mp4')})

    def test_health_and_observation(self):
        self.assertFalse(self.client.get('/health').json['extra_gpu_model_loaded'])
        response=self.submit()
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['status'],'advisory_only')
        self.assertEqual(self.worker.last,(DATA,'.mp4'))

    def test_bad_context_fails_before_inference(self):
        context=dict(CONTEXT,recipe_id=41)
        self.assertEqual(self.submit(context).status_code,400)
        self.assertFalse(hasattr(self.worker,'last'))

    def test_worker_busy_propagates(self):
        def busy(*args):raise WorkerError(429,'busy')
        self.worker.predict=busy
        self.assertEqual(self.submit().status_code,429)

    def test_worker_hash_mismatch_is_not_presented_as_evidence(self):
        def wrong(*args):
            r=result();r['media_sha256']='wrong';return r
        self.worker.predict=wrong
        self.assertEqual(self.submit().status_code,502)

    def test_existing_model4_envelope_roundtrip(self):
        record=self.submit().json
        response=self.client.post('/v1/cosmos/combine-model4',json={'cosmos':record,'model4':amy()})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['model4_response'],amy())

    def test_invalid_and_oversized_uploads(self):
        self.assertEqual(self.client.post('/v1/cosmos/observe').status_code,400)
        self.app.config['MAX_CONTENT_LENGTH']=32
        self.assertEqual(self.submit().status_code,413)

if __name__=='__main__':unittest.main()
