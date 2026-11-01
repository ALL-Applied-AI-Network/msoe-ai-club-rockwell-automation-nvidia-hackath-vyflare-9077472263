"""Optional native acquisition and all-or-nothing refinement of a fill's timing."""
from copy import deepcopy
import hashlib
import logging
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image

from .timing import LIMITS, VERSION, analyze, accept_visit
from .trace import Config, stream_score


def trace_bins(path):
    with Image.open(path) as image:
        if image.size != (640,480): raise ValueError('Invalid timing frame geometry')
        pixels=np.asarray(image.convert('RGB'),dtype=np.float32)
    background=np.median(np.concatenate((pixels[100:140,282:295],pixels[100:140,324:337]),axis=1),axis=1)
    return (pixels[100:140,296:318]-background[:,None,:]).reshape(20,2,22,3).mean(axis=1)


def plan(visits):
    windows=[];jobs={};fallback={};used=0.0
    for index,visit in enumerate(visits):
        _,base=accept_visit(visit,[])
        if visit['flags']:
            fallback[index]=base;continue
        departure=visit['departure_interval_seconds']
        if departure is None:
            fallback[index]={**base,'reason':'MISSING_STATION_DEPARTURE'};continue
        hypotheses=[]
        for episode in visit['episodes']:
            for kind in ('start','end'):
                interval=episode[kind+'_interval_seconds']
                if interval is None:continue
                hypotheses.append({'order':episode['order'],'kind':kind,
                    'lower':max(visit['first_stationary_seconds'],interval[1]-LIMITS['history_seconds']),
                    'upper':min(departure[0],interval[1]+LIMITS['forward_seconds'])})
        merged=[]
        for lo,hi in sorted((h['lower'],h['upper']) for h in hypotheses):
            if hi<=lo:continue
            if merged and lo<=merged[-1][1]:merged[-1][1]=max(hi,merged[-1][1])
            else:merged.append([lo,hi])
        if not merged:
            fallback[index]={**base,'reason':'NATIVE_CONTEXT_EMPTY'};continue
        seconds=sum(hi-lo for lo,hi in merged)
        if seconds>LIMITS['maximum_visit_seconds'] or used+seconds>LIMITS['maximum_video_seconds'] or len(windows)+len(merged)>300:
            fallback[index]={**base,'reason':'NATIVE_REVIEW_RESOURCE_LIMIT'};continue
        used+=seconds;clip_ids=[]
        for clip,(lo,hi) in enumerate(merged):
            uid=f'timing_{index:03}_{clip:03}';clip_ids.append(uid)
            windows.append({'id':uid,'lower':lo,'upper':hi})
        jobs[index]={'hypotheses':hypotheses,'clip_ids':clip_ids,'unique_seconds':seconds}
    return windows,jobs,fallback


def refine_visits(visits, events, event_folder, decoder, source, folder, config):
    """No recipes or labels are inputs. Flags and original color window survive."""
    output=deepcopy(visits);windows,jobs,fallback=plan(visits)
    for index,metadata in fallback.items():output[index]['timing_refinement']=metadata
    if not windows:return output
    try:
        manifest=decoder.decode('windows',source,folder,windows)
        allowed={w['id'] for w in windows};by_clip={uid:[] for uid in allowed}
        for record in manifest:
            clip=record['id'].rsplit('_',1)[0]
            if clip not in allowed:raise ValueError('Unexpected timing frame identity')
            by_clip[clip].append(record)
        for window in windows:
            rows=by_clip[window['id']]
            if not rows or any(not window['lower']-1e-6<=r['actual_seconds']<=window['upper']+1e-6 for r in rows):
                raise ValueError('Incomplete or misassigned timing windows')
    except (OSError,ValueError,KeyError,subprocess.SubprocessError):
        logging.getLogger(__name__).warning('Native timing review unavailable; retaining original observations',exc_info=True)
        for index in jobs:
            _,metadata=accept_visit(visits[index],[])
            output[index]['timing_refinement']={**metadata,'reason':'NATIVE_REVIEW_UNAVAILABLE'}
        return output
    for index,job in jobs.items():
        visit=visits[index]
        try:
            arrival=next(r for r in events if abs(r['actual_seconds']-visit['first_stationary_seconds'])<1e-6)
            reference=Path(event_folder)/(arrival['id']+'.jpg');baseline=trace_bins(reference)
            rows=[]
            for clip in job['clip_ids']:
                for record in by_clip[clip]:
                    path=Path(folder)/(record['id']+'.png')
                    rows.append({'seconds':record['actual_seconds'],'score':stream_score(trace_bins(path),baseline,Config(**config)),
                        'evidence_id':record['id'],'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
            rows.sort(key=lambda r:r['seconds'])
            diagnostics=[{**h,'diagnostic':analyze([r for r in rows if h['lower']-1e-6<=r['seconds']<=h['upper']+1e-6],h['kind'])}
                for h in job['hypotheses']]
            episodes,metadata=accept_visit(visit,diagnostics)
            metadata.update(unique_review_seconds=job['unique_seconds'],native_frames=rows,
                arrival_reference={'evidence_id':arrival['id'],'actual_seconds':arrival['actual_seconds'],
                    'sha256':hashlib.sha256(reference.read_bytes()).hexdigest()})
            output[index]['episodes']=episodes
            output[index]['timing_refinement']=metadata
        except (OSError,ValueError,KeyError,StopIteration):
            _,metadata=accept_visit(visit,[])
            output[index]['timing_refinement']={**metadata,'reason':'NATIVE_VISIT_EVIDENCE_INVALID'}
    return output
