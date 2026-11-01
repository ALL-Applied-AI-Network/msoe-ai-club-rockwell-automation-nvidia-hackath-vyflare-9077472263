"""Fresh full-recording pixel tracking; no recipe writes or model calls.

Run from the repository: PYTHONPATH=backend .venv/bin/python
backend/scripts/smoke_geometry_tracking.py --output /absolute/output/path
Requires the same local macOS decoder as the existing recorded observer.
"""
import argparse
import json
from pathlib import Path
import time

from recipes.geometry_api import GeometryService, observation_geometry


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--video-root',type=Path,default=Path('cosmos-original-dataset/videos'))
    parser.add_argument('--observations',type=Path,help='Optional frozen observation JSON; joined after pixel tracking, never used for detection')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    service=GeometryService(args.video_root.resolve(),args.output.resolve()/'cache')
    try:
        summaries=[]
        for video in ('video-1','video-2'):
            service.start(video)
            while True:
                with service.lock:status=service.jobs[video]['state'];progress=service.jobs[video].get('progress',0)
                print(video,status,progress,flush=True)
                if status!='processing':break
                time.sleep(5)
            result=service.get(video)
            if status!='complete':raise RuntimeError(result.get('error','Geometry processing failed'))
            if args.observations:
                observations=json.loads(args.observations.read_text())['observations']
                result['observations']=[observation_geometry(o,result['frames']) for o in observations
                    if o.get('video_id')==video and o.get('source_lineage',{}).get('video_sha256')==result['source_sha256']]
            frames=result['frames'];tracked=sum(any(d['status']=='TRACKING' for d in f['detections']) for f in frames)
            surfaces=sum(any(d['surface'] for d in f['detections']) for f in frames)
            (args.output/(video+'-geometry.json')).write_text(json.dumps(result,indent=2,allow_nan=False))
            summaries.append({'video_id':video,'frames':len(frames),'tracked_frames':tracked,'visible_surface_frames':surfaces,
                'source_sha256':result['source_sha256'],'implementation_sha256':result['implementation_sha256'],
                'recipe_writes':0,'counts_are_accuracy':False})
        (args.output/'summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
    finally:service.close()


if __name__=='__main__':main()
