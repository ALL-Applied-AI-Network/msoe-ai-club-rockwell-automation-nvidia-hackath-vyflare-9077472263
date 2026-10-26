import io
import unittest
from unittest.mock import patch
from PIL import Image
from app import create_app
from measurements import MeasurementsModel


class MeasurementsTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app({"measurements": MeasurementsModel()},
                                 {"TESTING": True, "MODEL_MODE": "real"}).test_client()

    def post(self, prompt):
        image = Image.new("RGB", (100, 100), "red")
        image.paste("blue", (50, 0, 100, 100))
        stream = io.BytesIO(); image.save(stream, "PNG"); stream.seek(0)
        return self.client.post("/predict", data={"image": (stream, "source.png"),
            "model": "measurements", "frame_id": "known-regions", "prompt": prompt})

    def test_selected_region_and_abstention(self):
        response = self.post('{"roi":[0.5,0,0.5,1]}')
        self.assertEqual(response.status_code, 200)
        result = response.json["result"]
        self.assertEqual(result["mean_rgb"], [0, 0, 255])
        self.assertEqual(result["region_pixels"], 5000)
        self.assertEqual(result["decision"], "UNABLE_TO_DECIDE")
        self.assertIsNone(result["volume_ml"])
        self.assertEqual(response.json["mode"], "real")

    def test_out_of_bounds_and_corrupt_roi_are_rejected(self):
        for prompt in ['{"roi":[0.9,0,0.5,1]}', '{bad', '{"roi":[true,0,1,1]}']:
            with self.subTest(prompt=prompt):
                self.assertEqual(self.post(prompt).status_code, 422)
        self.assertEqual(self.post('{"roi":[0,0,1,1]}').status_code, 200)

    def test_all_white_does_not_become_a_pass(self):
        result = MeasurementsModel().predict(Image.new("RGB", (10,10), "white"), "{}")
        self.assertEqual(result["decision"], "UNABLE_TO_DECIDE")

    def test_configured_gateway_token_is_required(self):
        with patch.dict("os.environ", {"INFERENCE_TOKEN": "local-test-token"}):
            self.assertEqual(self.post("{}").status_code, 401)
            self.assertEqual(self.client.get("/health").status_code, 200)

if __name__ == "__main__":
    unittest.main()
