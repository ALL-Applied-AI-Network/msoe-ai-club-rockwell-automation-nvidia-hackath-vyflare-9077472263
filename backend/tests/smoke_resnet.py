"""Opt-in real-weight smoke test; first run downloads torchvision weights."""
import io
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['MODEL_MODE'] = 'real'
os.environ['ENABLED_MODELS'] = 'resnet18'
os.environ['RESNET_DEVICE'] = 'cpu'
os.environ['RESNET_CHECKPOINT'] = ''
os.environ['TORCH_HOME'] = str(Path(__file__).resolve().parents[1] / '.model-cache')
from PIL import Image
from app import create_app
image = io.BytesIO()
Image.new('RGB', (224, 224), (130, 90, 40)).save(image, 'JPEG')
image.seek(0)
client = create_app().test_client()
response = client.post('/predict', data={'image': (image, 'test.jpg'), 'frame_id': 'smoke-1'})
assert response.status_code == 200, response.json
assert response.json['mode'] == 'real'
predictions = response.json['result']['predictions']
assert len(predictions) == 5
assert all(0 <= item['score'] <= 1 for item in predictions)
print('Real ResNet-18 CPU inference passed:', response.json['inference_ms'], 'ms')
print('Synthetic image verifies execution and response shape, not classification accuracy.')
