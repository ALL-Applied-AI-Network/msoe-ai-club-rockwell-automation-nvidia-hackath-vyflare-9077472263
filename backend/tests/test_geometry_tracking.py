import base64
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from flask import Flask
import numpy as np
from PIL import Image

from recipes.geometry_api import GeometryService, create_geometry_blueprint, observation_geometry
from recipes.geometry_tracking import GeometryTracker, detect_surface


def scene(surface=335,fill=True):
    a=np.full((480,640,3),180,dtype=np.uint8)
    # Stable glass/body edges, rim and base; no recipe/timing labels.
    a[75:418,280:284]=45;a[75:418,338:342]=45
    a[75:78,280:342]=80;a[416:420,280:342]=80
    a[200:265,250:385]=25
    if fill:a[surface:415,288:336]=[12,65,110]
    return a


class GeometryTests(unittest.TestCase):
    def test_geometry_is_measured_and_surface_requires_temporal_confirmation(self):
        tracker=GeometryTracker();a=scene()
        first=tracker.step(a,0);second=tracker.step(a,.25)
        self.assertEqual(first['detections'][0]['status'],'CONFIRMING')
        d=second['detections'][0];self.assertEqual(d['status'],'TRACKING');self.assertIsNotNone(d['surface'])
        self.assertLess(abs(d['surface']['y1']*480-335),8)
        self.assertGreater(d['box']['height'],.65)
        third=tracker.step(scene(surface=328),.5)['detections'][0]
        self.assertEqual(d['track_id'],third['track_id']);self.assertLess(third['surface']['y1'],d['surface']['y1'])
    def test_blank_view_and_wrong_resolution_do_not_assert_vials(self):
        self.assertEqual(GeometryTracker().step(np.zeros((480,640,3),dtype=np.uint8),0)['detections'],[])
        with self.assertRaises(ValueError):GeometryTracker().step(np.zeros((720,1280,3)),0)
    def test_hidden_or_empty_surface_is_not_fabricated(self):
        tracker=GeometryTracker();a=scene(surface=250);tracker.step(a,0)
        self.assertIsNone(tracker.step(a,.25)['detections'][0]['surface'])
        empty=scene(fill=False);self.assertIsNone(detect_surface(empty.astype(float),290,330,75,418)[0])
    def test_shading_band_inside_blue_liquid_is_not_a_new_surface(self):
        a=scene(surface=250).astype(float);a[315:400,288:336]*=.5
        self.assertIsNone(detect_surface(a,290,330,75,418)[0])
    def test_surface_disappearance_hides_line_immediately(self):
        tracker=GeometryTracker();tracker.step(scene(),0);self.assertIsNotNone(tracker.step(scene(),.25)['detections'][0]['surface'])
        self.assertIsNone(tracker.step(scene(fill=False),.5)['detections'][0]['surface'])
    def test_capture_gap_and_absence_do_not_reuse_identity(self):
        tracker=GeometryTracker();tracker.step(scene(),0);first=tracker.step(scene(),.25)['detections'][0]['track_id']
        gap=tracker.step(scene(),1);self.assertIn('INPUT_GAP_IDENTITY_RESET',gap['issues'])
        second=tracker.step(scene(),1.25)['detections'][0]['track_id'];self.assertNotEqual(first,second)
        tracker.step(np.full((480,640,3),180,dtype=np.uint8),1.5)
        tracker.step(scene(),1.75);third=tracker.step(scene(),2)['detections'][0]['track_id'];self.assertNotEqual(second,third)
    def test_motion_breaks_identity_and_hides_surface(self):
        tracker=GeometryTracker();tracker.step(scene(),0);first=tracker.step(scene(),.25)['detections'][0]['track_id']
        moving=scene();moving[200:265,250:385]=90
        f=tracker.step(moving,.5)['detections'][0];self.assertEqual(f['status'],'MOVING');self.assertIsNone(f['surface'])
        tracker.step(moving,.75);second=tracker.step(moving,1)['detections'][0]['track_id'];self.assertNotEqual(first,second)
    def test_timestamps_are_monotonic_and_finite(self):
        tracker=GeometryTracker();tracker.step(scene(),1)
        for t in (1,0,-1,float('nan'),True):
            with self.assertRaises(ValueError):tracker.step(scene(),t)
    def test_observer_join_remains_supplemental_and_does_not_assign_recipe(self):
        tracker=GeometryTracker();tracker.step(scene(),0);frame=tracker.step(scene(),.25)
        o={'vial_id':'V1-V01','observation_id':'test','source_episode_intervals':[{'start':[0,.1]}],'departure_interval_seconds':[.5,.6]}
        result=observation_geometry(o,[frame]);self.assertEqual(result['tracked_samples'],1)
        self.assertTrue(result['identity_continuous']);self.assertFalse(result['affects_recipe_decision']);self.assertNotIn('recipe_id',result)


class GeometryApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.service=GeometryService(self.tmp.name,Path(self.tmp.name)/'cache');self.addCleanup(self.service.close)
        app=Flask(__name__);app.register_blueprint(create_geometry_blueprint(self.service));self.client=app.test_client()
    def payload(self,pixels=None):
        buffer=BytesIO();Image.fromarray(scene() if pixels is None else pixels).save(buffer,format='JPEG',quality=92)
        return {'image':'data:image/jpeg;base64,'+base64.b64encode(buffer.getvalue()).decode(),'captured_at':0}
    def session(self):return self.client.post('/api/geometry/sessions',json={}).json['session_id']
    def test_session_frame_and_delete(self):
        key=self.session();url=f'/api/geometry/sessions/{key}/frame';payload=self.payload()
        self.assertEqual(self.client.post(url,json=payload).status_code,200)
        self.assertEqual(self.client.post(url,json=payload).status_code,400)
        self.assertEqual(self.client.delete(f'/api/geometry/sessions/{key}').status_code,204)
        self.assertEqual(self.client.post(url,json={**payload,'captured_at':1}).status_code,404)
    def test_bad_images_fields_and_dimensions(self):
        url=f'/api/geometry/sessions/{self.session()}/frame'
        for payload in ({},self.payload(np.zeros((10,10,3),dtype=np.uint8)),{'image':'data:image/jpeg;base64,invalid','captured_at':0}):
            self.assertEqual(self.client.post(url,json=payload).status_code,400)
    def test_session_limit_and_expiry(self):
        for _ in range(8):self.session()
        self.assertEqual(self.client.post('/api/geometry/sessions',json={}).status_code,409)
        with patch('recipes.geometry_api.monotonic',return_value=10**12):
            self.assertEqual(self.client.post('/api/geometry/sessions',json={}).status_code,201)
    def test_recording_allowlist_and_missing_sources(self):
        self.assertEqual(self.client.post('/api/geometry/recordings/video-3',json={}).status_code,404)
        self.assertEqual(self.client.get('/api/geometry/recordings/video-1').status_code,404)

class GeometryRecoveryTests(unittest.TestCase):
    def test_exposure_spike_can_recover_without_using_changing_liquid_pixels(self):
        tracker=GeometryTracker();tracker.step(scene(),0);first=tracker.step(scene(),.25)['detections'][0]['track_id']
        changed=scene();changed[200:265,250:385]+=3
        # Changing liquid or printed label at the center is not holder identity.
        changed[200:265,290:335]=140
        self.assertEqual(tracker.step(changed,.5)['detections'][0]['status'],'MOVING')
        tracker.step(changed,.75);recovered=tracker.step(changed,1)['detections'][0]
        self.assertEqual(recovered['track_id'],first)

class GeometryAuthTests(unittest.TestCase):
    def test_application_applies_token_and_origin_checks_to_tracking(self):
        import os
        from app import create_app
        with patch.dict(os.environ,{'INFERENCE_TOKEN':'geometry-test-secret'}):
            app=create_app({}, {'TESTING':True,'TRACKER_SCHEDULER_ENABLED':False,'RECIPE_DEMO_ENABLED':False})
            self.addCleanup(app.extensions['geometry_service'].close)
            self.addCleanup(app.extensions['tracker_manager'].shutdown)
            client=app.test_client();url='/api/geometry/sessions'
            self.assertEqual(client.post(url,json={}).status_code,401)
            self.assertEqual(client.post(url,json={},headers={'Authorization':'Bearer geometry-test-secret'}).status_code,201)
            self.assertEqual(client.post(url,json={},headers={'Authorization':'Bearer geometry-test-secret','Origin':'https://foreign.example'}).status_code,403)

class RecordedPixelRegressionTests(unittest.TestCase):
    def test_real_visible_boundary_and_hidden_surface(self):
        folder=Path(__file__).parent/'fixtures/geometry'
        for name,visible in [('video-2-22s.png',True),('video-1-29s.png',False)]:
            with self.subTest(name=name),Image.open(folder/name) as image:
                a=np.asarray(image.convert('RGB'));tracker=GeometryTracker();tracker.step(a,0)
                detection=tracker.step(a,.25)['detections'][0]
                self.assertEqual(detection['surface'] is not None,visible)
                if visible:self.assertLess(abs(detection['surface']['y1']*480-379),8)
                self.assertLess(abs(detection['box']['x']*640-278),12)
                self.assertLess(abs(detection['box']['y']*480-76),12)

class GeometrySourceRevisionTests(unittest.TestCase):
    def test_replacing_source_invalidates_loaded_geometry(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'vial_fill_video_1.mp4';source.write_bytes(b'first')
            service=GeometryService(root,root/'cache');self.addCleanup(service.close)
            stat=source.stat();service.jobs['video-1']={'state':'complete','frames':[], 'source_revision':[stat.st_size,stat.st_mtime_ns]}
            self.assertEqual(service.get('video-1')['state'],'complete')
            source.write_bytes(b'a different recording')
            self.assertEqual(service.get('video-1')['state'],'idle')

class GeometryQueueTests(unittest.TestCase):
    def test_two_allowlisted_sources_queue_once_without_unbounded_jobs(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            for n in (1,2):(root/f'vial_fill_video_{n}.mp4').write_bytes(b'test source')
            service=GeometryService(root,root/'cache');self.addCleanup(service.close)
            service.jobs['video-1']={'state':'processing','progress':0,'frames':[]}
            with patch('recipes.recorded_producer.NativeDecoder.capability',return_value={'available':True}),patch.object(service.executor,'submit') as submit:
                self.assertEqual(service.start('video-2')['state'],'processing')
                service.start('video-2');submit.assert_called_once()
