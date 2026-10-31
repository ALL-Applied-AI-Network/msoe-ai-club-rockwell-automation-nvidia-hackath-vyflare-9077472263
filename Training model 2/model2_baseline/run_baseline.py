"""Step 4: frozen ResNet18 features, linear head, grouped evaluation.

Usage: python run_baseline.py
All hyperparameters come from common.CONFIG and were fixed before evaluation.
"""
import csv

import cv2
import numpy as np
import torch
import torchvision
from PIL import Image, ImageOps
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from common import ART, CONFIG, DATA, OUT, write_json

MEAN_RGB = (124, 116, 104)                 # ImageNet mean, used for padding and masks
CROP = (250, 40, 390, 430)                 # x0, y0, x1, y1 on the 640x480 station frame
OVERLAY_Y = 435                            # rows from here down carry the burned-in timestamp
MODES = ("crop", "full")                   # crop is primary; full frame is the shortcut comparison
SEED = CONFIG["seed"]


def letterbox(img, size=CONFIG["input_size"]):
    h, w = img.shape[:2]
    s = max(h, w)
    canvas = np.full((s, s, 3), MEAN_RGB, np.uint8)
    y, x = (s - h) // 2, (s - w) // 2
    canvas[y:y + h, x:x + w] = img
    return cv2.resize(canvas, (size, size), interpolation=cv2.INTER_AREA)


def station_input(rgb, mode, rng=None):
    """Mask the overlay, optionally augment, crop (crop mode) and letterbox."""
    rgb = rgb.copy()
    rgb[OVERLAY_Y:] = MEAN_RGB
    x0, y0, x1, y1 = CROP if mode == "crop" else (0, 0, rgb.shape[1], rgb.shape[0])
    dx = dy = 0
    if rng is not None:
        dx = int(round(rng.uniform(-0.04, 0.04) * (x1 - x0)))
        dy = int(round(rng.uniform(-0.04, 0.04) * (y1 - y0)))
    if mode == "crop":
        img = rgb[y0 + dy:y1 + dy, x0 + dx:x1 + dx]
    else:
        img = cv2.warpAffine(rgb, np.float32([[1, 0, dx], [0, 1, dy]]), (rgb.shape[1], rgb.shape[0]),
                             borderMode=cv2.BORDER_REPLICATE)
    if rng is not None:
        img = np.clip(img.astype(np.float32) + rng.normal(0, 0.01 * 255, img.shape), 0, 255).astype(np.uint8)
    return letterbox(img)


def phone_input(path):
    img = np.array(ImageOps.exif_transpose(Image.open(path)).convert("RGB"))
    return letterbox(img)


class Backbone:
    def __init__(self):
        weights = torchvision.models.ResNet18_Weights.IMAGENET1K_V1
        self.net = torchvision.models.resnet18(weights=weights).eval()
        self.net.fc = torch.nn.Identity()
        for p in self.net.parameters():
            p.requires_grad_(False)
        self.mean = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
        self.std = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)

    def tensor(self, images):
        x = torch.from_numpy(np.stack(images)).permute(0, 3, 1, 2).float() / 255.0
        return (x - self.mean) / self.std

    @torch.no_grad()
    def __call__(self, images):
        return self.net(self.tensor(images)).numpy()


def load_inputs():
    vials = {v["vial_key"]: v for v in csv.DictReader(open(OUT / "vials_manifest.csv", encoding="utf-8"))}
    frames = [f for f in csv.DictReader(open(OUT / "frames_manifest.csv", encoding="utf-8")) if f["valid"] == "True"]
    return vials, frames


def compute_features(frames, backbone):
    cache = ART / "features.npz"
    if cache.exists():
        data = np.load(cache, allow_pickle=True)
        return data["feats"].item()
    feats = {}
    for i, f in enumerate(frames):
        rgb = cv2.cvtColor(cv2.imread(str(ART / f["image"])), cv2.COLOR_BGR2RGB)
        for mode in MODES:
            rng = np.random.default_rng(SEED + i)
            images = [station_input(rgb, mode)] + [station_input(rgb, mode, rng) for _ in range(CONFIG["augment_copies"])]
            feats[(f["vial_key"], f["tag"], mode)] = backbone(images)
    np.savez(cache, feats=np.array(feats, dtype=object))
    return feats


def vial_features(vial_key, frames, feats, mode, augmented):
    rows = [feats[(f["vial_key"], f["tag"], mode)] for f in frames if f["vial_key"] == vial_key]
    return np.concatenate([r if augmented else r[:1] for r in rows])


def fit_head(train_keys, vials, frames, feats, mode):
    X, y, w = [], [], []
    per_class = {}
    for k in train_keys:
        per_class[vials[k]["intended_recipe_id"]] = per_class.get(vials[k]["intended_recipe_id"], 0) + 1
    for k in train_keys:
        fx = vial_features(k, frames, feats, mode, augmented=True)
        recipe = vials[k]["intended_recipe_id"]
        X.append(fx)
        y += [recipe] * len(fx)
        w += [1.0 / (len(fx) * per_class[recipe])] * len(fx)
    X, w = np.concatenate(X), np.array(w) * len(y) / sum(w)
    scaler = StandardScaler().fit(X)
    clf = LogisticRegression(C=CONFIG["head_C"], max_iter=CONFIG["head_max_iter"])
    clf.fit(scaler.transform(X), y, sample_weight=w)
    train_acc = float((clf.predict(scaler.transform(X)) == np.array(y)).mean())
    return scaler, clf, train_acc


def score(scaler, clf, fx):
    probs = clf.predict_proba(scaler.transform(fx)).mean(axis=0)
    order = np.argsort(probs)[::-1]
    return probs, [(clf.classes_[i], float(probs[i])) for i in order]


def prediction_row(experiment, mode, split, v, n_frames, classes, ranked, train_acc):
    top, top_score = ranked[0]
    accepted = top_score >= CONFIG["accept_threshold"]
    intended = v["intended_recipe_id"]
    return {
        "experiment": experiment, "mode": mode, "split": split, "vial_key": v["vial_key"],
        "intended_recipe_id": intended, "visual_quality_label": v["visual_quality_label"], "eval_role": v["eval_role"],
        "first_vial_flag": v["first_vial_flag"], "batch_preceded_by_recipe_id": v["batch_preceded_by_recipe_id"],
        "recording_id": v["recording_id"], "batch_position": v["batch_position"], "n_valid_frames": n_frames,
        "intended_in_training": intended in classes, "training_classes": " ".join(classes),
        "predicted_recipe_id": top, "top_score": round(top_score, 4),
        "second_recipe_id": ranked[1][0] if len(ranked) > 1 else "", "second_score": round(ranked[1][1], 4) if len(ranked) > 1 else "",
        "status": "accepted_observation" if accepted else "unknown_uncertain",
        "matches_intended": top == intended, "accepted_and_matches": accepted and top == intended,
        "head_train_frame_accuracy": round(train_acc, 4),
    }


def run(vials, frames, feats):
    have_frames = {f["vial_key"] for f in frames}
    usable = {k: v for k, v in vials.items() if k in have_frames and not v["quarantine"]}
    eligible = [k for k, v in usable.items() if v["train_eligible"] == "True"]
    preds = []

    for mode in MODES:
        # A/C: physical-vial folds (fold p holds out batch position p in every batch).
        for fold in sorted({v["cv_fold"] for v in usable.values()}, key=int):
            train = [k for k in eligible if usable[k]["cv_fold"] != fold]
            scaler, clf, acc = fit_head(train, vials, frames, feats, mode)
            classes = list(clf.classes_)
            for k, v in usable.items():
                if v["cv_fold"] == fold:
                    fx = vial_features(k, frames, feats, mode, augmented=False)
                    preds.append(prediction_row("cv_physical_vial", mode, f"fold{fold}", v, len(fx), classes,
                                                score(scaler, clf, fx)[1], acc))

        # B: unfamiliar recipes, withholding identical-proportion recipes together.
        recipes = sorted({usable[k]["intended_recipe_id"] for k in eligible}, key=int)
        grouped = {str(r) for g in CONFIG["proportion_groups"] for r in g}
        groups = [[str(r) for r in g] for g in CONFIG["proportion_groups"]] + [[r] for r in recipes if r not in grouped]
        for group in groups:
            train = [k for k in eligible if usable[k]["intended_recipe_id"] not in group]
            scaler, clf, acc = fit_head(train, vials, frames, feats, mode)
            for k in eligible:
                if usable[k]["intended_recipe_id"] in group:
                    fx = vial_features(k, frames, feats, mode, augmented=False)
                    preds.append(prediction_row("unfamiliar_recipe", mode, "withheld_" + "+".join(group), usable[k],
                                                len(fx), list(clf.classes_), score(scaler, clf, fx)[1], acc))

        # D: recording generalization for the only recipe with two labeled recordings.
        recs = sorted({usable[k]["recording_id"] for k in eligible if usable[k]["intended_recipe_id"] == "99"})
        for rec in recs:
            held = [k for k in eligible if usable[k]["intended_recipe_id"] == "99" and usable[k]["recording_id"] == rec]
            train = [k for k in eligible if k not in held]
            scaler, clf, acc = fit_head(train, vials, frames, feats, mode)
            for k in held:
                fx = vial_features(k, frames, feats, mode, augmented=False)
                preds.append(prediction_row("recording_holdout_99", mode, "heldout_" + rec, usable[k], len(fx),
                                            list(clf.classes_), score(scaler, clf, fx)[1], acc))
    return preds, eligible


def phone_eval(final_heads, backbone, vials):
    """Phone photos scored by the final heads; the same physical vials are in training."""
    rows = []
    media = {m["path"]: m for m in csv.DictReader(open(OUT / "media_manifest.csv", encoding="utf-8"))}
    for path in sorted(DATA.rglob("*.jpg")):
        rel = path.relative_to(DATA).as_posix()
        m = media["data/" + rel]
        if m["use"] != "separate phone-camera evaluation":
            continue
        v = vials[m["mapped_vial_keys"]]
        fx = backbone([phone_input(path)])
        for mode, (scaler, clf, _) in final_heads.items():
            ranked = score(scaler, clf, fx)[1]
            rows.append({
                "photo": "data/" + rel, "photo_sha256": m["sha256"], "model_mode": mode, "vial_key": v["vial_key"],
                "intended_recipe_id": v["intended_recipe_id"], "visual_quality_label": v["visual_quality_label"],
                "eval_role": v["eval_role"], "first_vial_flag": v["first_vial_flag"],
                "test_type": "camera transfer (vial's station frames were in training)" if v["train_eligible"] == "True"
                else "camera transfer (vial never trained on)",
                "predicted_recipe_id": ranked[0][0], "top_score": round(ranked[0][1], 4),
                "status": "accepted_observation" if ranked[0][1] >= CONFIG["accept_threshold"] else "unknown_uncertain",
                "matches_intended": ranked[0][0] == v["intended_recipe_id"],
            })
    return rows


def export_head(scaler, clf, eligible, path):
    write_json(path, {
        "model": "Model 2 recipe classifier baseline", "config_version": CONFIG["config_version"],
        "backbone": CONFIG["backbone"], "backbone_weights_url": torchvision.models.ResNet18_Weights.IMAGENET1K_V1.url,
        "backbone_sha256": CONFIG["backbone_sha256"],
        "preprocessing": {"version": "station-crop-v1", "input": "640x480 station frame, RGB",
                          "overlay_mask_rows_from": OVERLAY_Y, "crop_xyxy": list(CROP), "letterbox_fill_rgb": list(MEAN_RGB),
                          "resize": [CONFIG["input_size"], CONFIG["input_size"]], "interpolation": "INTER_AREA",
                          "normalize_mean": [0.485, 0.456, 0.406], "normalize_std": [0.229, 0.224, 0.225],
                          "frames": "early post-flow +0.05/+0.15/+0.25 s after end of flow; frames with visible stream rejected"},
        "classes": list(clf.classes_), "scaler_mean": scaler.mean_.tolist(), "scaler_scale": scaler.scale_.tolist(),
        "coef": clf.coef_.tolist(), "intercept": clf.intercept_.tolist(),
        "aggregation": CONFIG["aggregation"], "accept_threshold": CONFIG["accept_threshold"],
        "calibrated": False, "calibration_version": None,
        "score_semantics": "uncalibrated softmax recipe-resemblance score; not a probability of correctness or of a good vial",
        "training_vials": sorted(eligible),
    })


def main():
    torch.manual_seed(SEED)
    vials, frames = load_inputs()
    backbone = Backbone()
    feats = compute_features(frames, backbone)
    preds, eligible = run(vials, frames, feats)

    final_heads = {mode: fit_head(eligible, vials, frames, feats, mode) for mode in MODES}
    for k, v in vials.items():  # full-model predictions for every usable vial (deployment view)
        if any(f["vial_key"] == k for f in frames) and not v["quarantine"]:
            for mode, (scaler, clf, acc) in final_heads.items():
                fx = vial_features(k, frames, feats, mode, augmented=False)
                preds.append(prediction_row("final_model_all_eligible", mode, "trained_on_all_eligible", v, len(fx),
                                            list(clf.classes_), score(scaler, clf, fx)[1], acc))
    export_head(*final_heads["crop"][:2], eligible, OUT / "model" / "model2_head_crop.json")
    export_head(*final_heads["full"][:2], eligible, OUT / "model" / "model2_head_fullframe_comparison.json")

    for name, rows in (("predictions_per_vial.csv", preds), ("predictions_phone_photos.csv", phone_eval(final_heads, backbone, vials))):
        with open(OUT / name, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    print("predictions:", len(preds), "eligible training vials:", len(eligible))


if __name__ == "__main__":
    main()
