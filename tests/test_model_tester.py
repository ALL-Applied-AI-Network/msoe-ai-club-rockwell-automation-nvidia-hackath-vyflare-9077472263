import io
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
try:
    from serve_spark_adapter import create_app
except ModuleNotFoundError as error:
    if error.name!='flask':raise
    create_app=None


class FakeRuntime:
    identity={'adapter':'test'}
    def predict(self,path,mode):
        self.upload_path=path
        return dict(outputs={'adapter':{'raw_text':'{}'}},media_info={},media_kind='video',prompt='test')


@unittest.skipIf(create_app is None,'Requires Flask in the Spark serving environment')
class TesterTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.runtime=FakeRuntime();self.root=Path(self.directory.name)
        self.app=create_app(self.runtime,self.root);self.client=self.app.test_client()

    def submit(self,client=None):
        return (client or self.client).post('/predict',data={'media':(io.BytesIO(b'test-video'),'vial.mp4'),'mode':'adapter'})

    def test_page_and_health(self):
        self.assertIn(b'VyFlare vial model tester',self.client.get('/').data)
        self.assertTrue(self.client.get('/health').json['ready'])

    def test_inference_cleans_upload(self):
        response=self.submit();self.assertEqual(response.status_code,200)
        self.assertFalse(self.runtime.upload_path.exists())
        self.assertEqual(len(response.json['media_sha256']),64)

    def test_feedback_requires_explicit_submission(self):
        result=self.submit().json
        self.assertEqual(list(self.root.iterdir()),[])
        response=self.client.post('/feedback',json={'run_id':result['run_id'],'human_sequence':'blue > green'})
        self.assertEqual(response.status_code,200)
        saved=json.loads((self.root/(result['run_id']+'.json')).read_text())
        self.assertEqual(saved['feedback']['status'],'submitted_for_review_not_training_ground_truth')

    def test_invalid_requests(self):
        self.assertEqual(self.client.post('/predict').status_code,400)
        self.assertEqual(self.client.post('/predict',data={'media':(io.BytesIO(b'x'),'bad.exe')}).status_code,415)
        self.assertEqual(self.client.post('/feedback',json={'run_id':'unknown'}).status_code,404)

    def test_upload_size_limit(self):
        self.app.config['MAX_CONTENT_LENGTH']=32
        self.assertEqual(self.submit().status_code,413)

    def test_concurrent_request_is_rejected(self):
        entered=threading.Event();release=threading.Event();original=self.runtime.predict
        def slow(path,mode):
            entered.set();release.wait(5);return original(path,mode)
        self.runtime.predict=slow
        worker=threading.Thread(target=lambda:self.submit(self.app.test_client()))
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            self.assertEqual(self.submit().status_code,429)
        finally:
            release.set();worker.join(5)


if __name__=='__main__':unittest.main()
