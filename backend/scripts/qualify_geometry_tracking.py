"""Recorded-only qualification from source-linked decoded frames; no bank writes.

--frames contains video-N-source.json and video-N-frames/*.jpg produced by the
native decoder. --decode can populate these from the installed recordings first.
Surface labels are read only after detection. They are developmental review,
not independent ground truth. See recipes/tracker_qualification.md.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image

from recipes.geometry_tracking import CONFIG, GeometryTracker
from recipes.geometry_api import observation_geometry
from recipes.recorded_producer import NativeDecoder, file_sha


def save(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--frames',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--decode',action='store_true')
    parser.add_argument('--videos',type=Path,default=Path('cosmos-original-dataset/videos'))
    parser.add_argument('--observations',type=Path,default=Path('backend/tests/fixtures/two_fill_observations.json'))
    parser.add_argument('--surface-labels',type=Path,default=Path('backend/tests/fixtures/geometry_qualification/surface-review-labels.json'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True);args.frames.mkdir(parents=True,exist_ok=True)
    if args.decode:
        with TemporaryDirectory(prefix='qualify-decoder-') as temp:
            decoder=NativeDecoder(Path(temp))
            for n in (1,2):
                source=args.videos/f'vial_fill_video_{n}.mp4';manifest=args.frames/f'video-{n}-source.json'
                if manifest.exists():
                    if json.loads(manifest.read_text())['source_sha256']!=file_sha(source):raise ValueError('Existing evidence source hash changed')
                    continue
                records=decoder.decode('events',source,args.frames/f'video-{n}-frames')
                save(manifest,{'source_sha256':file_sha(source),'records':records})
    observations=json.loads(args.observations.read_text())['observations'];all_frames={};all_observations=[];video_summaries=[]
    for n in (1,2):
        source=json.loads((args.frames/f'video-{n}-source.json').read_text());tracker=GeometryTracker();frames=[]
        if args.videos.exists() and file_sha(args.videos/f'vial_fill_video_{n}.mp4')!=source['source_sha256']:raise ValueError('Source video hash mismatch')
        for i,r in enumerate(source['records']):
            with Image.open(args.frames/f'video-{n}-frames'/(r['id']+'.jpg')) as image:
                if image.size!=(640,480):raise ValueError('Qualification image geometry changed')
                pixels=np.asarray(image.convert('RGB'))
            frames.append({**tracker.step(pixels,r['actual_seconds']),'frame_id':r['id']})
            if i%500==0:print('Tracking',n,i,flush=True)
        windows=[observation_geometry(o,frames) for o in observations if o['video_id']==f'video-{n}' and o['source_lineage']['video_sha256']==source['source_sha256']]
        overlaps=[{'left':a['vial_id'],'right':b['vial_id'],'ids':sorted(set(a['track_ids'])&set(b['track_ids']))} for a,b in zip(windows,windows[1:]) if set(a['track_ids'])&set(b['track_ids'])]
        save(args.output/f'video-{n}-qualified.json',{'config':CONFIG,'source_sha256':source['source_sha256'],'frames':frames,'observations':windows,'adjacent_id_overlaps':overlaps,'recipe_writes':0})
        all_frames[n]={f['frame_id']:f for f in frames};all_observations.extend(windows)
        video_summaries.append({'video':n,'frames':len(frames),'single_id_windows':sum(len(w['track_ids'])==1 for w in windows),'fill_windows':len(windows),'adjacent_id_overlaps':overlaps})
    # Read labels after pixel processing; they never affect association/detection.
    labels=json.loads(args.surface_labels.read_text());surface_rows=[]
    for label in labels['items']:
        n=label['video'];path=args.frames/f'video-{n}-frames'/(label['frame_id']+'.jpg')
        if file_sha(path)!=label['image_sha256']:raise ValueError('Reviewed pixel evidence changed')
        f=all_frames[n][label['frame_id']];d=next((d for d in f['detections'] if d['position']=='Filling Position'),None)
        surface=d and d['surface'];y=surface['y1']*480 if surface else None;kind=label['review_status'];band=label['y_band_pixels']
        if kind=='VISIBLE_APPROXIMATE':outcome='SUPPORTED_LINE' if y is not None and band[0]<=y<=band[1] else 'OUTSIDE_REVIEW_BAND' if y is not None else 'MISSED_VISIBLE_BOUNDARY'
        elif kind=='AMBIGUOUS_FOAM_OR_OCCLUSION':outcome='UNQUALIFIED_AMBIGUOUS_LINE' if y is not None else 'AMBIGUOUS_WITHHELD'
        else:outcome='UNSUPPORTED_LINE' if y is not None else 'CORRECTLY_WITHHELD'
        surface_rows.append({**label,'predicted_y':y,'outcome':outcome})
    save(args.output/'surface-evaluation.json',surface_rows)
    save(args.output/'qualification-summary.json',{'config':CONFIG,'videos':video_summaries,'fill_windows':len(all_observations),
        'single_id_windows':sum(len(w['track_ids'])==1 for w in all_observations),
        'strict_continuity_windows':sum(w['identity_continuous'] for w in all_observations),
        'bounded_recoveries':sum(len(w['bounded_detection_recoveries']) for w in all_observations),
        'surface_results':dict(Counter(r['outcome'] for r in surface_rows)),
        'surface_labels_sha256':hashlib.sha256(args.surface_labels.read_bytes()).hexdigest(),
        'independent_validation':False,'recipe_writes':0,'eligibility_rules_implemented':False,'live_tested':False})


if __name__=='__main__':main()
