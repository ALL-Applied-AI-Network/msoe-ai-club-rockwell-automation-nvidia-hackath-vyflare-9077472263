import io
import unittest
from unittest.mock import patch
from PIL import Image
from app import create_app
from models import MockModel, SafetyBlocked

class APITests(unittest.TestCase):
    def setUp(self):
        self.model = MockModel('resnet18')
        self.app = create_app({'resnet18': self.model, 'cosmos': MockModel('cosmos')},
                              {'TESTING': True, 'MODEL_MODE': 'mock'})
        self.client = self.app.test_client()

    def post(self, **overrides):
        image = io.BytesIO()
        Image.new('RGB', (32, 24), 'red').save(image, 'JPEG')
        image.seek(0)
        data = {'image': (image, 'frame.jpg'), 'frame_id': '42', 'model': 'resnet18'}
        data.update(overrides)
        return self.client.post('/predict', data=data)

    def test_roundtrip(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['frame_id'], '42')
        self.assertEqual(response.json['result']['image_size'], [32, 24])
        self.assertTrue(response.json['result']['mock'])

    def test_cosmos_routing(self):
        self.assertEqual(self.post(model='cosmos').json['result']['model'], 'cosmos')

    def test_paired_inference(self):
        with patch.object(self.model, 'predict', wraps=self.model.predict) as resnet:
            response = self.post(model='cosmos', include_resnet='true')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json['results']), {'resnet18', 'cosmos'})
        self.assertEqual(response.json['results']['resnet18']['model'], 'resnet18')
        self.assertEqual(response.json['results']['cosmos']['model'], 'cosmos')
        resnet.assert_called_once()

    def test_paired_requires_resnet(self):
        client = create_app({'cosmos': MockModel('cosmos')},
                            {'TESTING': True, 'MODEL_MODE': 'mock'}).test_client()
        response = client.post('/predict', data={
            'frame_id': '42', 'model': 'cosmos', 'include_resnet': 'true'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('disabled', response.json['error'])

    def test_invalid_pairing_flag(self):
        self.assertEqual(self.post(include_resnet='yes').status_code, 400)

    def test_paired_failure_releases_gate(self):
        with patch.object(self.model, 'predict', side_effect=RuntimeError('failed')):
            with self.assertLogs(self.app.logger, level='ERROR'):
                response = self.post(model='cosmos', include_resnet='true')
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('results', response.json)
        self.assertEqual(self.post().status_code, 200)

    def test_allowed_preflight(self):
        response = self.client.options('/predict', headers={
            'Origin': 'http://localhost:3000', 'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'Content-Type'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Access-Control-Allow-Origin'], 'http://localhost:3000')

    def test_rejected_origin(self):
        response = self.client.post('/predict', headers={'Origin': 'https://elsewhere.example'})
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('Access-Control-Allow-Origin', response.headers)

    def test_missing_image(self):
        self.assertEqual(self.client.post('/predict', data={'frame_id': '1'}).status_code, 400)

    def test_bad_frame_id(self):
        self.assertEqual(self.post(frame_id='').status_code, 400)

    def test_bad_model(self):
        self.assertEqual(self.post(model='unknown').status_code, 400)

    def test_corrupt_image(self):
        self.assertEqual(self.post(image=(io.BytesIO(b'bad'), 'bad.jpg')).status_code, 400)
        self.assertEqual(self.post().status_code, 200)

    def test_body_limit(self):
        self.app.config['MAX_CONTENT_LENGTH'] = 100
        self.assertEqual(self.post().status_code, 413)

    def test_busy_and_health(self):
        with self.app.extensions['inference_gate']:
            self.assertEqual(self.post().status_code, 429)
            self.assertTrue(self.client.get('/health').json['busy'])
        self.assertEqual(self.post().status_code, 200)

    def test_failure_releases_gate(self):
        with patch.object(self.model, 'predict', side_effect=RuntimeError('broken model')):
            with self.assertLogs(self.app.logger, level='ERROR'):
                response = self.post()
            self.assertEqual(response.status_code, 500)
            self.assertNotIn('broken model', response.json['error'])
        self.assertEqual(self.post().status_code, 200)

    def test_safety_block(self):
        with patch.object(self.model, 'predict', side_effect=SafetyBlocked('Blocked')):
            self.assertEqual(self.post().status_code, 422)
        self.assertEqual(self.post().status_code, 200)

    def test_unknown_route_json(self):
        response = self.client.get('/absent')
        self.assertEqual(response.status_code, 404)
        self.assertIsNotNone(response.json)

if __name__ == '__main__':
    unittest.main()
