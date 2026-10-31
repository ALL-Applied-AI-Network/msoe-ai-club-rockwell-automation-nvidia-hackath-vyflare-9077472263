"""Step 2: extract early post-flow frames (+0.05/+0.15/+0.25 s after end_s) per vial.

Also saves one in-flow reference (end_s - 0.5 s) used only for visual review.
Frames are written losslessly as PNG; source videos are opened read-only.
"""
import csv

import cv2

from common import ART, CONFIG, OUT, TM2, sha256

REVIEW_OFFSET = -0.5


def main():
    vials = list(csv.DictReader(open(OUT / "vials_manifest.csv", encoding="utf-8")))
    targets = {}  # video -> list of (time, vial_key, tag)
    for v in vials:
        if v["quarantine"]:
            continue
        end = float(v["end_s"])
        for off in [REVIEW_OFFSET] + CONFIG["post_flow_offsets_s"]:
            tag = "review_m050" if off < 0 else f"post{int(round(off * 100)):03d}"
            targets.setdefault(v["video_source"], []).append((end + off, v["vial_key"], tag))

    rows = []
    out_dir = ART / "frames"
    out_dir.mkdir(parents=True, exist_ok=True)
    for video, items in targets.items():
        items.sort()
        cap = cv2.VideoCapture(str(TM2 / video))
        i, frame_idx = 0, -1
        while i < len(items):
            ok, frame = cap.read()
            if not ok:
                break
            frame_idx += 1
            pts = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            while i < len(items) and pts >= items[i][0] - 1e-6:
                target, key, tag = items[i]
                path = out_dir / f"{key}_{tag}.png"
                cv2.imwrite(str(path), frame)
                rows.append({"vial_key": key, "tag": tag, "video_source": video, "target_s": round(target, 4),
                             "frame_index": frame_idx, "frame_pts_s": round(pts, 4),
                             "image": path.relative_to(ART).as_posix(), "image_sha256": sha256(path)})
                i += 1
        cap.release()
        print(video, "extracted", sum(r["video_source"] == video for r in rows), "of", len(items))

    with open(OUT / "frames_raw.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
