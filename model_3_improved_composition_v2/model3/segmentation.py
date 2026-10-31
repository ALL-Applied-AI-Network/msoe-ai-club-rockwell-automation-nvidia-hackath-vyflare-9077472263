"""Offline vial segmentation for recorded videos (dataset building and evaluation).

Each conveyor move is a burst of motion around the vial, so the frames between two moves belong to one
vial. Per vial this picks an empty-vial window (just after arrival) and a finished-vial window (the last
stable second before the next move). It looks at the whole recording, so it is an offline tool: a live
tracker must make the same choices from a frame buffer (see REPORT.md, integration).

This does not emit tracker events (DISPENSE_*, FILLING_COMPLETED). A conveyor move is not proof that
filling completed, and nothing here measures dispenses.
"""
from __future__ import annotations

import cv2
import numpy as np


def scan_video(path: str, cfg: dict) -> tuple[np.ndarray, np.ndarray, float]:
    """One pass: per-frame median RGB inside the liquid ROI, and motion energy in the motion box."""
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    x0, y0, x1, y1 = cfg["preprocessing"]["liquid_roi_xyxy"]
    mx0, my0, mx1, my1 = cfg["segmentation"]["motion_box_xyxy"]
    colour, motion, prev = [], [], None
    while True:
        ok, f = cap.read()
        if not ok:
            break
        colour.append(np.median(f[y0:y1, x0:x1, ::-1].reshape(-1, 3), 0))
        g = cv2.cvtColor(f[my0:my1, mx0:mx1], cv2.COLOR_BGR2GRAY).astype(np.float32)
        motion.append(0.0 if prev is None else float(np.abs(g - prev).mean()))
        prev = g
    return np.array(colour), np.array(motion), fps


def segment(colour: np.ndarray, motion: np.ndarray, fps: float, cfg: dict) -> list[dict]:
    """Frame windows per vial. Frame numbers are positions in the file (fps claims are not trusted)."""
    s = cfg["segmentation"]
    n = len(motion)
    events = []
    for i in np.where(motion > s["motion_spike"])[0]:
        if events and i - events[-1][-1] <= fps * 3:
            events[-1].append(i)
        else:
            events.append([i])
    bounds = [0] + [e[-1] for e in events] + [n - 1]
    out = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        if b - a < fps * s["min_vial_seconds"]:
            continue
        e0 = a + int(fps * s["empty_window_seconds_after_arrival"][0])
        e1 = a + int(fps * s["empty_window_seconds_after_arrival"][1])
        w = int(fps * s["finished_window_seconds"])
        full = None
        for end in range(b - int(fps * s["finished_window_end_before_move_seconds"]), e1 + int(fps * 4), -2):
            if np.ptp(colour[end - w:end], axis=0).max() < s["finished_window_max_colour_range_srgb"]:
                full = (end - w, end)
                break
        if full is None:
            out.append(dict(seg_start=int(a), seg_end=int(b), empty_start=e0, empty_end=e1,
                            full_start=None, full_end=None, colour_change=None, filled=False,
                            note="no stable finished window"))
            continue
        change = float(np.abs(colour[full[0]:full[1]].mean(0) - colour[e0:e1].mean(0)).max())
        out.append(dict(seg_start=int(a), seg_end=int(b), empty_start=e0, empty_end=e1,
                        full_start=full[0], full_end=full[1], colour_change=round(change, 1),
                        filled=change >= s["min_colour_change_srgb"],
                        note="" if change >= s["min_colour_change_srgb"] else "no colour change (no fill)"))
    return out


def read_frames(path: str, indices) -> dict[int, np.ndarray]:
    """RGB frames at the given file positions (sequential read; exact frame numbers)."""
    want = sorted(set(int(i) for i in indices))
    cap = cv2.VideoCapture(path)
    got, idx, k = {}, 0, 0
    while k < len(want):
        ok, f = cap.read()
        if not ok:
            break
        if idx == want[k]:
            got[idx] = f[:, :, ::-1].copy()
            k += 1
        idx += 1
    return got


def median_frame(frames: list[np.ndarray]) -> np.ndarray:
    return np.median(np.stack(frames), 0).astype(np.uint8)
