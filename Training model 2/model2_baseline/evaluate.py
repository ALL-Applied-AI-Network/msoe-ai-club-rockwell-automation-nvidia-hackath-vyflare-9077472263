"""Step 5: separate metrics per evaluation question, counted per independent vial."""
import csv
from collections import Counter, defaultdict

import numpy as np
from sklearn.metrics import f1_score

from common import CONFIG, OUT, write_json

T = CONFIG["accept_threshold"]


def load(name):
    return list(csv.DictReader(open(OUT / name, encoding="utf-8")))


def truthy(x):
    return x == "True"


def recognition(rows):
    y, p = [r["intended_recipe_id"] for r in rows], [r["predicted_recipe_id"] for r in rows]
    labels = sorted(set(y) | set(p), key=int)
    accepted = [r for r in rows if r["status"] == "accepted_observation"]
    recall = {}
    for rec in sorted(set(y), key=int):
        sub = [r for r in rows if r["intended_recipe_id"] == rec]
        recall[rec] = {"vials": len(sub), "correct": sum(truthy(r["matches_intended"]) for r in sub),
                       "accepted_correct": sum(truthy(r["accepted_and_matches"]) for r in sub)}
    scores = np.array([float(r["top_score"]) for r in rows])
    correct = np.array([truthy(r["matches_intended"]) for r in rows])
    return {
        "independent_vials": len(rows), "frames": sum(int(r["n_valid_frames"]) for r in rows),
        "accuracy_top1": round(float(correct.mean()), 4),
        "macro_f1_top1": round(float(f1_score(y, p, labels=sorted(set(y), key=int), average="macro", zero_division=0)), 4),
        "coverage_at_0.90": round(len(accepted) / len(rows), 4),
        "accepted_vials": len(accepted),
        "accepted_prediction_accuracy": round(sum(truthy(r["matches_intended"]) for r in accepted) / len(accepted), 4) if accepted else None,
        "per_recipe": recall,
        "confusion_matrix": {"labels": labels, "rows_true_cols_pred": [[sum(1 for a, b in zip(y, p) if a == t and b == q) for q in labels] for t in labels]},
        "calibration_check": {"mean_top_score": round(float(scores.mean()), 4), "top1_accuracy": round(float(correct.mean()), 4),
                              "note": "uncalibrated; no separate calibration data"},
    }


def acceptance(rows):
    acc = [r for r in rows if r["status"] == "accepted_observation"]
    return {
        "independent_vials": len(rows), "frames": sum(int(r["n_valid_frames"]) for r in rows),
        "false_acceptances_at_0.90": len(acc),
        "false_acceptance_rate": round(len(acc) / len(rows), 4) if rows else None,
        "accepted_as_intended_recipe": sum(truthy(r["accepted_and_matches"]) for r in rows),
        "top1_names_intended_recipe": sum(truthy(r["matches_intended"]) for r in rows),
        "vials": [{k: r[k] for k in ("vial_key", "intended_recipe_id", "batch_preceded_by_recipe_id", "predicted_recipe_id",
                                      "top_score", "status", "intended_in_training")} for r in rows],
    }


def main():
    preds, phone = load("predictions_per_vial.csv"), load("predictions_phone_photos.csv")
    vials = load("vials_manifest.csv")
    frames = load("frames_manifest.csv")
    valid = Counter(f["vial_key"] for f in frames if f["valid"] == "True")
    out = {"threshold": T, "score_semantics": "uncalibrated recipe-resemblance; not P(correct) or P(good vial)"}
    out["exclusions"] = [{"vial_key": v["vial_key"], "eval_role": v["eval_role"],
                          "reason": "; ".join(filter(None, [v["exclusion_reason"], "" if v["quarantine"] or valid.get(v["vial_key"])
                                                            else "no valid early post-flow frame (stream visible)"])),
                          "valid_frames": valid.get(v["vial_key"], 0)}
                         for v in vials if v["quarantine"] or valid.get(v["vial_key"], 0) == 0]
    for mode in ("crop", "holder", "full"):
        m = {}
        cv = [r for r in preds if r["experiment"] == "cv_physical_vial" and r["mode"] == mode]
        good = [r for r in cv if r["eval_role"] == "A_good_known"]
        assert all(truthy(r["intended_in_training"]) for r in good)
        m["A_good_known_recipe_cv"] = recognition(good)
        unf = [r for r in preds if r["experiment"] == "unfamiliar_recipe" and r["mode"] == mode]
        m["B_unfamiliar_good_recipes"] = acceptance(unf)
        by_group = defaultdict(list)
        for r in unf:
            by_group[r["split"]].append(r)
        m["B_by_withheld_group"] = {g: {"vials": len(rs), "false_acceptances": sum(r["status"] == "accepted_observation" for r in rs),
                                        "max_score": max(float(r["top_score"]) for r in rs)} for g, rs in by_group.items()}
        m["C_bad_first_vials"] = acceptance([r for r in cv if r["eval_role"] == "C_bad_first"])
        m["C_bad_later_vials"] = acceptance([r for r in cv if r["eval_role"] == "C_bad_later"])
        m["C_first_vials_labeled_good"] = acceptance([r for r in cv if r["eval_role"] == "C_first_vial_labeled_good"])
        rec = [r for r in preds if r["experiment"] == "recording_holdout_99" and r["mode"] == mode]
        m["D_recording_holdout_recipe99"] = {s: recognition([r for r in rec if r["split"] == s]) for s in sorted({r["split"] for r in rec})}
        m["unknown_quality_predictions_no_metrics"] = [
            {k: r[k] for k in ("vial_key", "intended_recipe_id", "first_vial_flag", "predicted_recipe_id", "top_score", "status")}
            for r in cv if r["eval_role"] == "unknown_quality"]
        m["head_train_frame_accuracy_by_fold"] = {r["split"]: r["head_train_frame_accuracy"] for r in cv}
        ph = [r for r in phone if r["model_mode"] == mode]
        # One photo per vial; these physical vials' station frames trained the final head.
        m["phone_photos_separate"] = {
            role: {"photos": len(rs), "accepted": sum(r["status"] == "accepted_observation" for r in rs),
                   "top1_matches_intended": sum(truthy(r["matches_intended"]) for r in rs),
                   "accepted_and_matches_intended": sum(r["status"] == "accepted_observation" and truthy(r["matches_intended"]) for r in rs)}
            for role, rs in ((role, [r for r in ph if r["eval_role"] == role]) for role in sorted({r["eval_role"] for r in ph}))}
        out[mode] = m
    write_json(OUT / "metrics.json", out)

    for mode in ("crop", "holder", "full"):
        m = out[mode]
        a = m["A_good_known_recipe_cv"]
        print(f"== {mode}")
        print(f" A good known: vials {a['independent_vials']} frames {a['frames']} acc {a['accuracy_top1']} macroF1 {a['macro_f1_top1']} "
              f"coverage {a['coverage_at_0.90']} accepted-acc {a['accepted_prediction_accuracy']} mean score {a['calibration_check']['mean_top_score']}")
        for key in ("B_unfamiliar_good_recipes", "C_bad_first_vials", "C_bad_later_vials", "C_first_vials_labeled_good"):
            b = m[key]
            print(f" {key}: vials {b['independent_vials']} FA {b['false_acceptances_at_0.90']} rate {b['false_acceptance_rate']} accepted-as-intended {b['accepted_as_intended_recipe']}")
        for s, d in m["D_recording_holdout_recipe99"].items():
            print(f" D {s}: vials {d['independent_vials']} acc {d['accuracy_top1']} coverage {d['coverage_at_0.90']}")
        print(" phone:", m["phone_photos_separate"])
        print(" train acc:", m["head_train_frame_accuracy_by_fold"])


if __name__ == "__main__":
    main()
