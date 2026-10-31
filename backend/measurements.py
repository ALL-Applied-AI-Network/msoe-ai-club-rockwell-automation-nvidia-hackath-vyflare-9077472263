"""CPU image measurements; no recipe, volume, or defect prediction is inferred."""
from PIL import ImageStat


class MeasurementsModel:
    def predict(self, image, prompt):
        # A user-selected crop is optional: normalized x,y,width,height.
        # Default to the complete image instead of assuming a camera geometry.
        import json
        roi = json.loads(prompt) if prompt.startswith("{") else {}
        if not isinstance(roi, dict):
            raise ValueError("ROI request must be an object")
        coordinates = roi.get("roi", [0, 0, 1, 1])
        if (not isinstance(coordinates, list) or len(coordinates) != 4
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in coordinates)):
            raise ValueError("ROI must be four normalized numbers")
        x, y, w, h = coordinates
        if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1-x and 0 < h <= 1-y):
            raise ValueError("ROI must be inside the image")
        box = (round(x*image.width), round(y*image.height),
               round((x+w)*image.width), round((y+h)*image.height))
        if box[2] <= box[0] or box[3] <= box[1]:
            raise ValueError("ROI is too small")
        crop = image.crop(box).convert("RGB")
        rgb = [round(v, 2) for v in ImageStat.Stat(crop).mean]
        return {"method": "roi-rgb/1.0", "provenance": "COMPUTED_RESULT",
                "mean_rgb": rgb, "color_hex": "#" + "".join(f"{round(v):02x}" for v in rgb),
                "roi": coordinates, "region_pixels": crop.width*crop.height,
                "decision": "UNABLE_TO_DECIDE", "volume_ml": None,
                "limitations": ["Mean pixel color of the selected region; not a segmented liquid measurement.",
                                "No calibrated recipe reference or physical volume is available."]}
