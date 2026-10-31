import io
import os
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import URLError

from PIL import Image
from werkzeug.serving import make_server

from app import create_app
from models import Cosmos3Model, MockModel, RemoteCosmosModel, SafetyBlocked, load_models


class TextSafetyTests(unittest.TestCase):
    def test_native_classifier_errors_are_not_treated_as_safe(self):
        adapter = Cosmos3Model.__new__(Cosmos3Model)
        classifier = SimpleNamespace(classify=lambda text: (_ for _ in ()).throw(
            RuntimeError('classifier unavailable')))
        adapter.pipe = SimpleNamespace(guardrails=SimpleNamespace(
            text=SimpleNamespace(safety_models=[classifier])))
        with self.assertRaises(RuntimeError):
            adapter._check_text('Describe a vial.')

    def test_native_classifier_labels(self):
        adapter = Cosmos3Model.__new__(Cosmos3Model)
        for label in ['Safe', 'Unsafe', 'Controversial']:
            classifier = SimpleNamespace(classify=lambda text: SimpleNamespace(label=label))
            adapter.pipe = SimpleNamespace(guardrails=SimpleNamespace(
                text=SimpleNamespace(safety_models=[classifier])))
            if label == 'Safe':
                adapter._check_text('Describe a vial.')
            else:
                with self.assertRaises(SafetyBlocked):
                    adapter._check_text('Describe a vial.')


class CosmosSwitchTests(unittest.TestCase):
    def setUp(self):
        self.worker_model = MockModel('cosmos')
        self.worker = create_app({'cosmos': self.worker_model},
                                 {'TESTING': True, 'MODEL_MODE': 'real'})
        self.server = make_server('127.0.0.1', 0, self.worker)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.env = patch.dict(os.environ, {
            'COSMOS_FULL_URL': f'http://127.0.0.1:{self.server.server_port}/predict',
            'COSMOS_FULL_REMOTE_MODEL': 'cosmos',
        })
        self.env.start()
        self.lite = MockModel('cosmos_lite')
        self.remote = RemoteCosmosModel()
        self.gateway = create_app({'cosmos_lite': self.lite, 'cosmos_full': self.remote},
                                  {'TESTING': True, 'MODEL_MODE': 'real'})
        self.client = self.gateway.test_client()

    def tearDown(self):
        self.env.stop()
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def post(self, model):
        data = io.BytesIO()
        Image.new('RGB', (32, 24), 'red').save(data, 'PNG')
        data.seek(0)
        return self.client.post('/predict', data={
            'image': (data, 'frame.png'), 'frame_id': 'frontend-42',
            'model': model, 'prompt': 'Inspect this vial. µ',
        })

    def test_lite_stays_local_and_full_reaches_worker(self):
        result = {'text': 'DGX result', 'execution': {
            'system': 'Linux', 'machine': 'aarch64', 'gpu': 'NVIDIA GB10',
            'hostname': 'test-dgx'}}
        with patch.object(self.worker_model, 'predict', return_value=result) as full:
            response = self.post('cosmos_lite')
            self.assertEqual(response.json['result']['model'], 'cosmos_lite')
            full.assert_not_called()
            response = self.post('cosmos_full')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['model'], 'cosmos_full')
            self.assertEqual(response.json['frame_id'], 'frontend-42')
            self.assertEqual(response.json['result']['text'], 'DGX result')
            self.assertEqual(full.call_args.args[0].size, (32, 24))
            self.assertEqual(full.call_args.args[1], 'Inspect this vial. µ')

    def test_full_rejects_worker_without_dgx_hardware(self):
        for execution in [None, {'system': 'Windows', 'machine': 'AMD64',
                                  'gpu': 'NVIDIA GB10'},
                          {'system': 'Linux', 'machine': 'aarch64', 'gpu': 'CPU'}]:
            with self.subTest(execution=execution), patch.object(
                    self.worker_model, 'predict', return_value={
                        'text': 'wrong worker', 'execution': execution}):
                self.assertEqual(self.post('cosmos_full').status_code, 502)

    def test_remote_safety_and_busy_release_gateway(self):
        with patch.object(self.worker_model, 'predict', side_effect=SafetyBlocked('blocked')):
            self.assertEqual(self.post('cosmos_full').status_code, 422)
        with self.worker.extensions['inference_gate']:
            response = self.post('cosmos_full')
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.headers['Retry-After'], '1')
        self.assertEqual(self.post('cosmos_lite').status_code, 200)

    def test_mock_worker_is_rejected(self):
        self.assertEqual(self.post('cosmos_full').status_code, 502)

    def test_unavailable_and_timeout_do_not_fall_back(self):
        for failure, expected in [(URLError('offline'), 503), (TimeoutError(), 504)]:
            with self.subTest(expected=expected), patch('models.request.urlopen', side_effect=failure):
                self.assertEqual(self.post('cosmos_full').status_code, expected)
            self.assertEqual(self.post('cosmos_lite').status_code, 200)

    def test_registry_routes_without_loading_remote_weights_locally(self):
        with patch.dict(os.environ, {'ENABLED_MODELS': 'resnet18,cosmos_lite,cosmos_full'}):
            with patch('models.ResNet18Model') as resnet, patch('models.Cosmos3Model') as lite:
                registry = load_models('real')
            self.assertIs(registry['cosmos_lite'], lite.return_value)
            self.assertIs(registry['resnet18'], resnet.return_value)
            self.assertIsInstance(registry['cosmos_full'], RemoteCosmosModel)
            lite.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
