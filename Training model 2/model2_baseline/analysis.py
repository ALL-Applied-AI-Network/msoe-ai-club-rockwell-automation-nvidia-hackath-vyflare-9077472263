"""Step 6: attribution, occlusion/shortcut tests and head-weight inspection.

Attribution maps show where the linear-head logit is sensitive; they do not by
themselves establish causal reliance. Occlusion tests re-score held-out vials with
regions masked, using the same fold heads trained on unmasked data.
"""
import csv
import hashlib
import io

import cv2
import numpy as np
import torch

from common import ART, CONFIG, OUT, write_json
from run_baseline import (CROP, MEAN_RGB, OVERLAY_Y, Backbone, compute_features, fit_head, letterbox, load_inputs,
                          score, station_input)

AN = OUT / "analysis"
# Regions in full-frame coordinates (inside the crop x 250-390, y 40-430).
REGIONS = {
    "above_holder (tube, label, nozzle)": (250, 40, 390, 200),
    "holder_band": (250, 200, 390, 245),
    "liquid_column_below_holder": (250, 245, 390, 430),
}


def state_hash(net):
    buf = io.BytesIO()
    torch.save({k: v.cpu() for k, v in net.state_dict().items()}, buf)
    return hashlib.sha256(buf.getvalue()).hexdigest()


def masked(rgb, box):
    out = rgb.copy()
    x0, y0, x1, y1 = box
    out[y0:y1, x0:x1] = MEAN_RGB
    return out


def frame_rgb(f):
    return cv2.cvtColor(cv2.imread(str(ART / f["image"])), cv2.COLOR_BGR2RGB)


def gradcam(backbone, scaler, clf, image, cls):
    net = backbone.net
    acts = {}
    handle = net.layer4.register_forward_hook(lambda m, i, o: acts.__setitem__("a", o))
    # Parameters stay frozen; an input that requires grad makes autograd build the graph.
    x = backbone.tensor([image]).requires_grad_(True)
    with torch.enable_grad():
        feat = net(x)
        idx = list(clf.classes_).index(cls)
        w = torch.tensor(clf.coef_[idx] / scaler.scale_, dtype=torch.float32)
        logit = (feat[0] * w).sum()
        grad = torch.autograd.grad(logit, acts["a"])[0][0]
    handle.remove()
    a = acts["a"][0].detach()
    cam = torch.relu((grad.mean(dim=(1, 2))[:, None, None] * a).sum(0)).numpy()
    cam = cv2.resize(cam / (cam.max() + 1e-8), image.shape[1::-1])
    heat = cv2.applyColorMap((cam * 255).astype(np.uint8), cv2.COLORMAP_JET)[:, :, ::-1]
    return (0.55 * image + 0.45 * heat).astype(np.uint8)


def main():
    vials, frames = load_inputs()
    backbone = Backbone()
    before = state_hash(backbone.net)
    feats = compute_features(frames, backbone)
    usable = {k: v for k, v in vials.items() if not v["quarantine"] and any(f["vial_key"] == k for f in frames)}
    eligible = [k for k, v in usable.items() if v["train_eligible"] == "True"]
    by_vial = {}
    for f in frames:
        by_vial.setdefault(f["vial_key"], []).append(f)
    result = {"caveat": "attribution shows sensitivity, not causal reliance; weights do not reveal ingredient composition"}

    # Occlusion / shortcut tests on held-out good vials, per fold.
    folds = sorted({usable[k]["cv_fold"] for k in usable}, key=int)
    tests = {"crop": [("none", None)] + list(REGIONS.items()),
             "full": [("none", None), ("vial_crop_region (background only)", CROP)]}
    occl = {}
    for mode, variants in tests.items():
        for fold in folds:
            train = [k for k in eligible if usable[k]["cv_fold"] != fold]
            scaler, clf, _ = fit_head(train, vials, frames, feats, mode)
            for k, v in usable.items():
                if v["cv_fold"] != fold or v["eval_role"] != "A_good_known":
                    continue
                for name, box in variants:
                    imgs = [station_input(frame_rgb(f) if box is None else masked(frame_rgb(f), box), mode) for f in by_vial[k]]
                    top, s = score(scaler, clf, backbone(imgs))[1][0]
                    d = occl.setdefault(f"{mode}: mask {name}", {"vials": 0, "top1_correct": 0, "accepted": 0, "accepted_correct": 0})
                    d["vials"] += 1
                    d["top1_correct"] += top == v["intended_recipe_id"]
                    d["accepted"] += s >= CONFIG["accept_threshold"]
                    d["accepted_correct"] += s >= CONFIG["accept_threshold"] and top == v["intended_recipe_id"]
    result["occlusion_cv_good_vials"] = occl

    # Head weights of the final crop model.
    scaler, clf, train_acc = fit_head(eligible, vials, frames, feats, "crop")
    coef = clf.coef_
    norms = {c: round(float(np.linalg.norm(w)), 3) for c, w in zip(clf.classes_, coef)}
    cos = coef @ coef.T / np.outer(np.linalg.norm(coef, axis=1), np.linalg.norm(coef, axis=1))
    pairs = sorted(((float(cos[i, j]), clf.classes_[i], clf.classes_[j]) for i in range(len(coef)) for j in range(i + 1, len(coef))), reverse=True)
    result["head"] = {"train_frame_accuracy": train_acc, "classes": list(clf.classes_), "coef_l2_norm": norms,
                      "most_similar_class_weight_pairs": [{"pair": f"{a}-{b}", "cosine": round(c, 3)} for c, a, b in pairs[:5]],
                      "backbone_frozen": True, "backbone_state_sha256_before": before}

    # Grad-CAM panels: (vial, class to explain, head trained without a group or None, caption).
    cases = [
        # Captions give the role only; the tile prints the computed outcome.
        ("field_v04", None, "good 41, CV fold"),
        ("field_v14", None, "good 60, CV fold"),
        ("v5_e15", None, "good 9, CV fold"),
        ("field_v25", None, "good 50, CV fold"),
        ("field_v17", None, "bad later 99, CV fold"),
        ("field_v11", None, "bad first 60, CV fold"),
        ("v5_e22", None, "bad first 12, CV fold"),
        ("v5_e25", None, "bad first 13, CV fold"),
        ("field_v07", ["99"], "good 99, recipe 99 withheld"),
        ("field_v12", ["60"], "good 60, recipe 60 withheld"),
    ]
    tiles = []
    for key, withheld, caption in cases:
        if withheld:
            sc, cl, _ = fit_head([k for k in eligible if usable[k]["intended_recipe_id"] not in withheld], vials, frames, feats, "crop")
        else:
            fold = usable[key]["cv_fold"]
            sc, cl, _ = fit_head([k for k in eligible if usable[k]["cv_fold"] != fold], vials, frames, feats, "crop")
        image = station_input(frame_rgb(by_vial[key][0]), "crop")
        top, s = score(sc, cl, backbone([image]))[1][0]
        tile = np.hstack([image, gradcam(backbone, sc, cl, image, top)])
        tile = cv2.copyMakeBorder(tile, 34, 0, 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255))
        cv2.putText(tile, f"{key}: {caption}", (4, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
        cv2.putText(tile, f"frame {by_vial[key][0]['tag']}: top {top} score {s:.3f}", (4, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
        tiles.append(tile)
    AN.mkdir(parents=True, exist_ok=True)
    grid = np.vstack([np.hstack(tiles[i:i + 2]) for i in range(0, len(tiles), 2)])
    cv2.imwrite(str(AN / "gradcam_crop_model.png"), cv2.cvtColor(grid, cv2.COLOR_RGB2BGR))

    result["head"]["backbone_state_sha256_after"] = state_hash(backbone.net)
    result["head"]["backbone_unchanged"] = result["head"]["backbone_state_sha256_before"] == result["head"]["backbone_state_sha256_after"]
    write_json(AN / "analysis.json", result)
    for k, d in occl.items():
        print(f"{k:55s} {d}")
    print(result["head"]["coef_l2_norm"], result["head"]["most_similar_class_weight_pairs"][:3], "backbone unchanged:", result["head"]["backbone_unchanged"])


if __name__ == "__main__":
    main()
