"""Build the vial-level dataset from the original videos (stills are not used; see REPORT.md, audit).

For every vial: segment the video automatically, take an empty-vial frame (median of the empty window)
and 4 individual finished frames spread over the last stable second before the conveyor moves, and
compute absorbance features (Model 3) and the notebook's RGB colour statistics (baseline).

Labels:
  video 5    recipe from labels/video5_vial_recipes.csv, matched by the labelled end_frame falling inside
             the detected vial segment. Batch position = order within the recipe's batch.
  field data recipe = first numeric folder (41, 50, 60, 99); run order from each video's .json started_at;
             volumes from recipes.xlsx (Recipe_Bank). Batch position = vials since the recipe changed.

Original data is read only. Every decision is written to the output (notes column, segments.csv).

Usage:
  python scripts/build_dataset.py --video5 path/vial_fill_video_5.mp4 --labels5 path/video5_vial_recipes.csv \
      --field-root path/field-data --recipes-xlsx path/recipes.xlsx [--out artifacts]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model3.preprocess import absorbance_features, colour_stats, load_config  # noqa: E402
from model3.segmentation import median_frame, read_frames, scan_video, segment  # noqa: E402

N_FINISHED = 4


def measure_run(video, cfg):
    colour, motion, fps = scan_video(str(video), cfg)
    segs = segment(colour, motion, fps, cfg)
    want = []
    for s in segs:
        if s["filled"]:
            s["empty_idx"] = list(range(s["empty_start"], s["empty_end"], 3))
            s["finished_idx"] = list(np.linspace(s["full_start"], s["full_end"] - 1, N_FINISHED).round().astype(int))
            want += s["empty_idx"] + s["finished_idx"]
    frames = read_frames(str(video), want)
    rows = []
    for s in segs:
        if not s["filled"]:
            continue
        empty = median_frame([frames[i] for i in s["empty_idx"]])
        for k, fi in enumerate(s["finished_idx"]):
            f = frames[fi]
            a = absorbance_features(empty, f, cfg)
            rgb = colour_stats(f)
            rows.append(dict(frame_index=int(fi), finished_k=k, captured_at_s=round(fi / fps, 3),
                             empty_start=s["empty_start"], empty_end=s["empty_end"],
                             seg_start=s["seg_start"], seg_end=s["seg_end"],
                             A_R=a["A"][0], A_G=a["A"][1], A_B=a["A"][2], liquid_coverage=a["liquid_coverage"],
                             full_R=a["full_median_rgb"][0], full_G=a["full_median_rgb"][1],
                             full_B=a["full_median_rgb"][2],
                             **{f"rgb_{n}": v for n, v in zip(
                                 ["mean_R", "mean_G", "mean_B", "std_R", "std_G", "std_B"], rgb)}))
    return segs, rows, fps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video5", required=True)
    ap.add_argument("--labels5", required=True)
    ap.add_argument("--field-root", required=True)
    ap.add_argument("--recipes-xlsx", required=True)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "artifacts"))
    a = ap.parse_args()
    cfg = load_config()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    all_rows, seg_log = [], []

    # ---------------- video 5
    lab = pd.read_csv(a.labels5).sort_values("vial").reset_index(drop=True)
    lab[["t100_ml", "t200_ml", "t400_ml"]] = lab[["t100_ml", "t200_ml", "t400_ml"]].fillna(0)
    lab["batch_position"] = lab.groupby("recipe_id").cumcount() + 1
    lab["prev_recipe_id"] = lab.recipe_id.shift(1)
    print("video 5 ...", flush=True)
    segs, rows, fps = measure_run(a.video5, cfg)
    run = Path(a.video5).name
    for i, s in enumerate(segs, 1):
        hit = lab[(lab.end_frame >= s["seg_start"]) & (lab.end_frame <= s["seg_end"])]
        s.update(session="video5", run_id=run, segment_no=i,
                 matched_vial=int(hit.vial.iloc[0]) if len(hit) == 1 else None)
        seg_log.append(s)
    for r in rows:
        s = next(s for s in segs if s["seg_start"] == r["seg_start"])
        if s["matched_vial"] is None:
            continue
        v = lab[lab.vial == s["matched_vial"]].iloc[0]
        note = []
        if v.start_frame < r["empty_end"]:
            note.append("fill began before the empty window: empty reference contains liquid")
        r.update(session="video5", run_id=run, vial_uid=f"video5:v{int(v.vial):02d}", vial_in_run=int(v.vial),
                 recipe_id=int(v.recipe_id), t100_ml=v.t100_ml, t200_ml=v.t200_ml, t400_ml=v.t400_ml,
                 batch_position=int(v.batch_position),
                 prev_recipe_id=None if v.batch_position > 1 or pd.isna(v.prev_recipe_id) else int(v.prev_recipe_id),
                 label_end_frame=int(v.end_frame), notes="; ".join(note))
        all_rows.append(r)

    # ---------------- field data
    bank = pd.read_excel(a.recipes_xlsx, sheet_name="Recipe_Bank")
    bank.columns = [str(c).strip() for c in bank.columns]
    bank = bank.set_index("Recipe ID")
    runs = []
    root = Path(a.field_root)
    for mp4 in sorted(root.rglob("*.mp4")):
        if "__MACOSX" in mp4.parts:
            continue
        rid = next(int(p) for p in mp4.relative_to(root).parts if p.isdigit())
        meta = mp4.with_suffix(".json")
        runs.append(dict(path=mp4, recipe_id=rid,
                         started_at=json.load(open(meta))["started_at"] if meta.exists() else ""))
    runs.sort(key=lambda r: r["started_at"])
    prev, since = None, 0
    for run in runs:
        print(f"{run['path'].name} ...", flush=True)
        segs, rows, fps = measure_run(run["path"], cfg)
        for i, s in enumerate(segs, 1):
            s.update(session="field_2026-10-28", run_id=run["path"].name, segment_no=i, matched_vial=None)
            seg_log.append(s)
        changed = run["recipe_id"] != prev
        if changed:
            since = 0
        ml = bank.loc[run["recipe_id"], ["T100 (mL)", "T200 (mL)", "T400 (mL)"]].fillna(0).astype(float)
        vial_no = 0
        for seg_start in sorted({r["seg_start"] for r in rows}):
            since += 1
            vial_no += 1
            for r in (r for r in rows if r["seg_start"] == seg_start):
                r.update(session="field_2026-10-28", run_id=run["path"].name,
                         vial_uid=f"field:{run['path'].stem}:v{vial_no}", vial_in_run=vial_no,
                         recipe_id=run["recipe_id"], t100_ml=ml.iloc[0], t200_ml=ml.iloc[1], t400_ml=ml.iloc[2],
                         batch_position=since, prev_recipe_id=prev if (changed and since == 1) else None,
                         label_end_frame=None, notes="")
                all_rows.append(r)
        prev = run["recipe_id"]

    df = pd.DataFrame(all_rows)
    tot = df[["t100_ml", "t200_ml", "t400_ml"]].sum(axis=1)
    assert (tot > 0).all(), "invalid total volume"
    for c, n in zip(["r100", "r200", "r400"], ["t100_ml", "t200_ml", "t400_ml"]):
        df[c] = df[n] / tot
    lead = ["session", "run_id", "vial_uid", "vial_in_run", "recipe_id", "t100_ml", "t200_ml", "t400_ml",
            "r100", "r200", "r400", "batch_position", "prev_recipe_id", "frame_index", "finished_k",
            "captured_at_s", "notes"]
    df = df[lead + [c for c in df.columns if c not in lead]]
    df.to_csv(out / "frame_features.csv", index=False)
    seg = pd.DataFrame(seg_log).drop(columns=["empty_idx", "finished_idx"], errors="ignore")
    seg.to_csv(out / "segments.csv", index=False)
    v = df.groupby("vial_uid").first()
    print(f"\n{len(df)} finished frames, {len(v)} vials -> {out/'frame_features.csv'}")
    print(v.groupby("session").size().to_string())
    unmatched = seg[(seg.session == "video5") & seg.filled & seg.matched_vial.isna()]
    print(f"video 5 filled segments without a label: {len(unmatched)}; "
          f"labelled vials without a segment: {30 - v[v.session == 'video5'].shape[0]}")


if __name__ == "__main__":
    main()
