import io
import sys
import tempfile
import threading
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
try:
    from PIL import Image
    from serve_spark_adapter import create_app
except ModuleNotFoundError as error:
    if error.name not in {'PIL','flask'}:raise
    create_app=None

class Runtime:
    identity={'adapter':'fixture-v1'}
    execution=dict(hostname='fixture-dgx',system='Linux',machine='aarch64',gpu='NVIDIA GB10')
    def predict(self,path,mode,prompt_override=None):
        self.received=(path,mode,prompt_override)
        return dict(outputs={'adapter':dict(raw_text='A green liquid.',parsed=None)})

@unittest.skipIf(create_app is None,'Flask and Pillow required')
class Model4WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.runtime=Runtime();self.app=create_app(self.runtime,Path(self.temp.name));self.client=self.app.test_client()

    def submit(self,client=None,**changes):
        stream=io.BytesIO();Image.new('RGB',(32,24),'green').save(stream,'PNG');stream.seek(0)
        body=dict(frame_id='backend-frame',model='cosmos',prompt='Describe this vial. µ',image=(stream,'frame.png'))
        body.update(changes)
        return (client or self.client).post('/backend/predict',data=body)

    def test_reference_response_and_prompt_contract(self):
        response=self.submit();self.assertEqual(response.status_code,200)
        body=response.json
        self.assertEqual((body['frame_id'],body['model'],body['mode']),('backend-frame','cosmos','real'))
        self.assertEqual(body['result']['text'],'A green liquid.')
        self.assertEqual(body['result']['execution'],self.runtime.execution)
        self.assertEqual(self.runtime.received[2],'Describe this vial. µ')
        self.assertFalse(self.runtime.received[0].exists())
        self.assertEqual(body['result']['safety']['status'],'not_provided_by_this_lora_worker')

    def test_bad_fields_and_corrupt_images(self):
        for fields in [dict(frame_id=''),dict(model='model4'),dict(prompt='')]:
            self.assertEqual(self.submit(**fields).status_code,400)
        self.assertEqual(self.submit(image=(io.BytesIO(b'broken'),'bad.png')).status_code,400)

    def test_verified_hardware_is_required(self):
        self.runtime.execution=dict(system='Windows',machine='AMD64',gpu='CPU')
        self.assertEqual(self.submit().status_code,503)

    def test_gate_is_shared_with_existing_predict_route(self):
        entered=threading.Event();release=threading.Event();original=self.runtime.predict
        def slow(*args,**kwargs):entered.set();release.wait(5);return original(*args,**kwargs)
        self.runtime.predict=slow
        worker=threading.Thread(target=lambda:self.submit(self.app.test_client()));worker.start()
        try:
            self.assertTrue(entered.wait(2))
            response=self.submit();self.assertEqual(response.status_code,429)
            self.assertEqual(response.headers['Retry-After'],'1')
            old=self.client.post('/predict',data={'media':(io.BytesIO(b'x'),'clip.mp4'),'mode':'adapter'})
            self.assertEqual(old.status_code,429)
        finally:release.set();worker.join(5)

    def test_runtime_failure_releases_gate(self):
        original=self.runtime.predict
        def fail(*args,**kwargs):raise RuntimeError('fixture failure')
        self.runtime.predict=fail
        self.assertEqual(self.submit().status_code,500)
        self.runtime.predict=original
        self.assertEqual(self.submit().status_code,200)

if __name__=='__main__':unittest.main()
