"""Step 0: no-flow boundary per vial (operator-approved 2026-10-31).

Recipes 5-14: end_s from video5_vial_recipes.csv (operator instruction).
Field vials: workbook end_s, moved later to the last frame with a visible stream
when flow is still visible after it; the stream must then stay absent for 1.0 s
before the next vial starts. Uses the frame_qc stream rule.
"""
import csv

import cv2

from common import FIELD_CONCAT, OUT, TM2, workbook_vials
from frame_qc import CENTER_LIMIT, PROFILE_LIMIT, stream_scores

VIDEO5_TIMING = TM2 / "video5_vial_recipes.csv"
SEARCH_S, CLEAR_S = 15.0, 1.0


def main():
    vials = workbook_vials()
    rows = []
    for r in csv.DictReader(open(VIDEO5_TIMING, encoding="utf-8")):
        rows.append({"vial_key": f"v5_e{int(r['vial']):02d}", "workbook_end_s": "", "end_s_used": float(r["end_s"]),
                     "start_s_used": float(r["start_s"]), "boundary_source": "video5_vial_recipes.csv end_s"})

    field = sorted((v for v in vials if v["vial_key"].startswith("field")), key=lambda v: v["start_s"])
    windows = []
    for i, v in enumerate(field):
        nxt = field[i + 1]["start_s"] if i + 1 < len(field) else v["end_s"] + SEARCH_S
        windows.append((v["end_s"], min(nxt, v["end_s"] + SEARCH_S), v))
    cap = cv2.VideoCapture(str(FIELD_CONCAT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    state = {v["vial_key"]: {"last_stream": None, "clear": 0, "done": False} for _, _, v in windows}
    while True:
        ok = cap.grab()
        if not ok:
            break
        t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        for lo, hi, v in windows:
            s = state[v["vial_key"]]
            if s["done"] or not lo - 1e-6 <= t <= hi:
                continue
            c, p = stream_scores(cap.retrieve()[1])
            if c >= CENTER_LIMIT or p >= PROFILE_LIMIT:
                s["last_stream"], s["clear"] = t, 0
            else:
                s["clear"] += 1
                s["done"] = s["clear"] >= int(CLEAR_S * fps)
    for _, _, v in windows:
        s = state[v["vial_key"]]
        if not s["done"]:
            raise RuntimeError(f"{v['vial_key']}: stream did not clear for {CLEAR_S} s before the next vial")
        moved = s["last_stream"] is not None
        rows.append({"vial_key": v["vial_key"], "workbook_end_s": v["end_s"],
                     "end_s_used": round(s["last_stream"], 4) if moved else v["end_s"], "start_s_used": v["start_s"],
                     "boundary_source": "measured: last visible-stream frame (stream continued past workbook end_s)" if moved
                     else "workbook end_s (no stream after it)"})
    with open(OUT / "flow_boundaries.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        if r["boundary_source"].startswith("measured"):
            print(r["vial_key"], r["workbook_end_s"], "->", r["end_s_used"])


if __name__ == "__main__":
    main()
