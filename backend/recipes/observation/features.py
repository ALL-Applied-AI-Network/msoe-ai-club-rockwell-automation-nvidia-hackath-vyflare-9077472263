"""Ported fixed 640 × 480 station features; source pixels only."""
import numpy as np

def frame_features(pixels, previous=None):
    if pixels.shape != (480,640,3):
        raise ValueError("Unsupported camera geometry; expected 640x480 RGB")
    a = pixels.astype(np.float32)
    gray = np.mean(a,axis=2)
    holder = gray[195:275,240:390]
    presence = float(np.mean(gray[210:260,260:355] < 80))
    difference = None if previous is None else np.abs(holder-previous)
    motion = None if difference is None else min(float(np.mean(difference[:,:38])),float(np.mean(difference[:,108:])))
    # Compare the stream's central columns with adjacent background at each row.
    # Avoid the hanging-drop zone next to the tip and printed labels lower down.
    stream = np.median(a[100:140,303:314],axis=1)
    sides = np.concatenate((a[100:140,282:295],a[100:140,324:337]),axis=1)
    background = np.median(sides,axis=1)
    delta = np.linalg.norm(stream-background,axis=1)
    chroma = stream.max(axis=1)-stream.min(axis=1)
    # Retain continuous descriptors; decision thresholds live in the observer.
    profile = {f"row_fraction_delta_{cut}":float(np.mean(delta>cut)) for cut in (10,15,20,25,30)}
    profile.update({f"row_fraction_chroma_{cut}":float(np.mean(chroma>cut)) for cut in (10,15,20,25)})
    profile.update({f"row_fraction_either_{c}_{d}":float(np.mean((chroma>c)|(delta>d)))
                    for c in (10,15,20) for d in (15,20,25)})
    signature = np.concatenate((holder[:,:40],holder[:,110:150]),axis=1).reshape(8,10,8,10).mean(axis=(1,3))
    liquid = np.median(a[370:394,299:325].reshape(-1,3),axis=0)
    return {"holder_dark_fraction":presence,"station_motion":motion,
        "stream_delta_median":float(np.median(delta)),"stream_delta_q75":float(np.quantile(delta,.75)),
        "stream_chroma_median":float(np.median(chroma)),**profile,
        "liquid_rgb":liquid.tolist(),"holder_signature":signature.reshape(-1).tolist(),
        "stream_contrast_signature":(stream-background).reshape(20,2,3).mean(axis=1).reshape(-1).tolist()},holder



def extract(pixels, previous=None):
    features, holder = frame_features(pixels, previous)
    a = pixels.astype(np.float32)
    background = np.median(np.concatenate((a[100:140,282:295], a[100:140,324:337]),axis=1),axis=1)
    features["trace_contrast_bins"] = (a[100:140,296:318]-background[:,None,:]).reshape(20,2,22,3).mean(axis=1)
    return features, holder
