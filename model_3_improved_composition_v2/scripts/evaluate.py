"""Evaluate Model 3 v2 and baselines on every split in artifacts/split_manifest.csv.

Methods (all trained only on the training-eligible vials of each fold, same frames, same splits):
  mean_composition   predict the training-set mean composition
  colour_linear      the original notebook's colour baseline (RGB mean/std of its vial crop, linear),
                     re-run on the corrected finished frames, projected onto the simplex
  model3_absorbance  Model 3 v2 via the inference adapter (same aggregation and quality rules as
                     deployment); reported ungated (all vials) and gated (status PREDICTED only)
The original notebook's ResNet-18 is not re-run here (no PyTorch in this environment); its own reported
numbers are quoted in REPORT.md and are not comparable (mislabelled stills, different frames).

Primary results are vial-level (median over a vial's 4 finished frames). Frame-level results are
reported separately; frames of one vial are correlated and not independent samples.

Usage: python scripts/evaluate.py  ->  artifacts/eval/{metrics.csv, vial_predictions.csv,
                                       frame_predictions.csv, eval_report.md}
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model3.fit import FEATURES, fit_checkpoint, fit_linear  # noqa: E402
from model3.inference import Model3Composition  # noqa: E402
from model3.preprocess import load_config, project_to_simplex  # noqa: E402

# Camera black floor per session (config "quality.black_floor_srgb" is per station). Video 5's camera
# reaches ~2 sRGB in its darkest vials; the Oct 28 field camera ~15.
SESSION_FLOOR = {"video5": 2.0, "field_2026-10-28": 15.0}
RGB = ["rgb_mean_R", "rgb_mean_G", "rgb_mean_B", "rgb_std_R", "rgb_std_G", "rgb_std_B"]
R = ["r100", "r200", "r400"]
OUT = ROOT / "artifacts" / "eval"


def folds(split: pd.DataFrame):
    v5 = split[split.session == "video5"]
    for k in sorted(v5.vial3fold_v5.dropna().unique()):
        yield "vial3fold_v5", f"pos{int(k)}", set(v5.vial_uid[v5.vial3fold_v5 == k])
    for r in sorted(v5.loro_v5.dropna().unique()):
        yield "loro_v5", f"recipe{int(r)}", set(v5.vial_uid[v5.loro_v5 == r])
    yield "cross_session", "field", set(split.vial_uid[split.cross_session == "test"])


def feats_of(rows: pd.DataFrame) -> list[dict]:
    return [dict(A=r[FEATURES].to_numpy(float), liquid_coverage=r.liquid_coverage,
                 full_median_rgb=r[["full_R", "full_G", "full_B"]].to_numpy(float)) for _, r in rows.iterrows()]


def main():
    cfg = load_config()
    frames = pd.read_csv(ROOT / "artifacts" / "frame_features.csv")
    split = pd.read_csv(ROOT / "artifacts" / "split_manifest.csv")
    eligible = set(split.vial_uid[split.training_eligible])
    vial_rows, frame_rows = [], []
    for scheme, fold, test_ids in folds(split):
        train = frames[frames.vial_uid.isin(eligible - test_ids)]
        test = frames[frames.vial_uid.isin(test_ids)]
        mean_pred = train[R].mean().to_numpy()
        Wc, bc = fit_linear(train[RGB].to_numpy(float), train[R].to_numpy(float))
        ckpt = fit_checkpoint(train, cfg, f"{scheme}/{fold}")
        adapters = {s: Model3Composition(checkpoint=ckpt, black_floor_srgb=f) for s, f in SESSION_FLOOR.items()}
        for vid, g in test.groupby("vial_uid"):
            meta = dict(scheme=scheme, fold=fold, vial_uid=vid, session=g.session.iloc[0],
                        recipe_id=int(g.recipe_id.iloc[0]), batch_position=int(g.batch_position.iloc[0]),
                        true_r100=g.r100.iloc[0], true_r200=g.r200.iloc[0], true_r400=g.r400.iloc[0])
            # vial level
            raw_c = Wc @ np.median(g[RGB].to_numpy(float), 0) + bc
            out = adapters[meta["session"]].predict_from_features(feats_of(g))
            raw_m = np.array(out["diagnostics"]["raw_unprojected"])
            for method, raw, status, flags in [
                ("mean_composition", mean_pred, "PREDICTED", ""),
                ("colour_linear", raw_c, "PREDICTED", ""),
                ("model3_absorbance", raw_m, out["status"], ";".join(out["quality_flags"]))]:
                p = project_to_simplex(raw)
                vial_rows.append(dict(**meta, method=method, status=status, quality_flags=flags,
                                      raw_valid=bool(np.all(raw >= -1e-6) and np.all(raw <= 1 + 1e-6)
                                                     and abs(raw.sum() - 1) < 0.01),
                                      pred_r100=p[0], pred_r200=p[1], pred_r400=p[2]))
            # frame level (no aggregation, no gate)
            for _, f in g.iterrows():
                pc = project_to_simplex(Wc @ f[RGB].to_numpy(float) + bc)
                o, b = np.array(ckpt["coef"]) @ f[FEATURES].to_numpy(float) + np.array(ckpt["intercept"])
                pm = project_to_simplex(np.array([1 - o - b, o, b]))
                for method, p in [("mean_composition", mean_pred), ("colour_linear", pc), ("model3_absorbance", pm)]:
                    frame_rows.append(dict(**meta, method=method, frame_index=int(f.frame_index),
                                           pred_r100=p[0], pred_r200=p[1], pred_r400=p[2]))

    OUT.mkdir(parents=True, exist_ok=True)
    vr, fr = pd.DataFrame(vial_rows), pd.DataFrame(frame_rows)
    for d in (vr, fr):
        for c in R:
            d[f"abs_err_{c}"] = (d[f"pred_{c}"] - d[f"true_{c}"]).abs() * 100      # percentage points
        d["mae_pp"] = d[[f"abs_err_{c}" for c in R]].mean(axis=1)
    vr.to_csv(OUT / "vial_predictions.csv", index=False)
    fr.to_csv(OUT / "frame_predictions.csv", index=False)

    # ---------------- metrics
    def summarise(d, fd):
        acc = d[d.status == "PREDICTED"]
        pos = d.batch_position
        return pd.Series({
            "vials": len(d), "coverage": round(len(acc) / len(d), 3),
            "MAE_pp_all": d.mae_pp.mean(), "MAE_pp_predicted_only": acc.mae_pp.mean() if len(acc) else np.nan,
            "MAE_pp_t100": d.abs_err_r100.mean(), "MAE_pp_t200": d.abs_err_r200.mean(),
            "MAE_pp_t400": d.abs_err_r400.mean(),
            "MAE_pp_pos1": d.mae_pp[pos == 1].mean(), "MAE_pp_pos2": d.mae_pp[pos == 2].mean(),
            "MAE_pp_pos3plus": d.mae_pp[pos >= 3].mean(),
            "MAE_pp_frame_level": fd.mae_pp.mean(),
            "raw_valid_rate": d.raw_valid.mean(), "output_valid_rate": 1.0})
    keys = ["scheme", "method"]
    m = pd.DataFrame([summarise(g, fr[(fr.scheme == k[0]) & (fr.method == k[1])]).rename(k)
                      for k, g in vr.groupby(keys)])
    m.index = pd.MultiIndex.from_tuples(m.index, names=keys)
    m = m.round(2)
    m.to_csv(OUT / "metrics.csv")

    model = vr[vr.method == "model3_absorbance"]
    per_recipe = (model.groupby(["scheme", "recipe_id"])
                  .agg(vials=("mae_pp", "size"), MAE_pp=("mae_pp", "mean"),
                       predicted=("status", lambda s: int((s == "PREDICTED").sum()))).round(2))
    cs = model[model.scheme == "cross_session"].copy()
    cs["gate"] = np.where(cs.status == "PREDICTED", "PREDICTED", "UNABLE_TO_ESTIMATE")
    flag_tab = []
    for flag in ["TOO_DARK", "CHANNEL_SATURATED_R", "CHANNEL_SATURATED_B", "CHANNEL_SATURATED_G",
                 "OUTSIDE_TRAINING_RANGE", "RAW_OUTSIDE_SIMPLEX", "FRAME_DISAGREEMENT", "NO_LIQUID_DETECTED"]:
        for sch, g in model.groupby("scheme"):
            has = g.quality_flags.fillna("").str.contains(flag)
            if has.any():
                flag_tab.append(dict(scheme=sch, flag=flag, vials=int(has.sum()),
                                     MAE_pp_flagged=round(g.mae_pp[has].mean(), 2),
                                     MAE_pp_unflagged=round(g.mae_pp[~has].mean(), 2)))
    flag_tab = pd.DataFrame(flag_tab)
    # like-for-like: steady vials (not 1st after a change; field also not 2nd), on the vials Model 3 accepts
    steady = (vr.session.eq("video5") & vr.batch_position.ge(2)) | (vr.session.ne("video5") & vr.batch_position.ge(3))
    accepted = set(model.loc[model.status == "PREDICTED", ["scheme", "vial_uid"]].itertuples(index=False, name=None))
    vr["model3_accepted"] = [(a, b) in accepted for a, b in zip(vr.scheme, vr.vial_uid)]
    like = (vr[steady & vr.model3_accepted].groupby(["scheme", "method"])
            .agg(vials=("mae_pp", "size"), MAE_pp=("mae_pp", "mean"),
                 MAE_pp_t100=("abs_err_r100", "mean"), MAE_pp_t200=("abs_err_r200", "mean"),
                 MAE_pp_t400=("abs_err_r400", "mean")).round(2))
    worst = (model.sort_values("mae_pp", ascending=False).head(12)
             [["scheme", "vial_uid", "recipe_id", "batch_position", "status", "quality_flags", "mae_pp"]].round(1))

    with open(OUT / "eval_report.md", "w") as fh:
        fh.write("# Model 3 v2 evaluation (generated by scripts/evaluate.py)\n\n")
        fh.write("Vial-level unless stated. Errors are absolute errors in percentage points (pp) of the "
                 "volume fractions, averaged over t100/t200/t400. Labels are commanded recipe settings.\n\n")
        fh.write("## Metrics by split and method\n\n" + m.reset_index().to_markdown(index=False) + "\n\n")
        fh.write("## Steady vials, same vials for every method (those Model 3 accepts)\n\n"
                 "Steady = video 5 batch position >= 2; field batch position >= 3 (the field data shows residue "
                 "in the 2nd vial after dark recipes). Errors on 1st/2nd vials after a recipe change mostly "
                 "reflect real carryover, because labels are the commanded recipe.\n\n"
                 + like.reset_index().to_markdown(index=False) + "\n\n")
        fh.write("## Model 3 by recipe\n\n" + per_recipe.reset_index().to_markdown(index=False) + "\n\n")
        fh.write("## Quality flags (Model 3)\n\n" + (flag_tab.to_markdown(index=False) if len(flag_tab) else "none")
                 + "\n\n")
        fh.write("## Largest errors (Model 3)\n\n" + worst.to_markdown(index=False) + "\n")
    pd.set_option("display.width", 250)
    print(m.reset_index()[["scheme", "method", "vials", "coverage", "MAE_pp_all", "MAE_pp_predicted_only",
                           "MAE_pp_pos1", "MAE_pp_pos2", "MAE_pp_pos3plus", "MAE_pp_frame_level",
                           "raw_valid_rate"]].to_string(index=False))
    print("\n", like.to_string())
    print("\n", per_recipe.to_string())
    print("\n", flag_tab.to_string(index=False))
    print("\n", worst.to_string(index=False))
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
