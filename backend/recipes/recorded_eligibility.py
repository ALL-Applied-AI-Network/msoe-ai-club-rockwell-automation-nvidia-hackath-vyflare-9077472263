"""Recorded-only identity/visibility eligibility, independent of recipe features.

Reports are produced from server-decoded pixels. No surface height, inferred
volume, browser overlay, recipe identity or reviewed label is an input.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from .geometry_tracking import CONFIG, VERSION as TRACKER_VERSION, IMPLEMENTATION_SHA

VERSION='recorded-tracking-eligibility/1'
POLICY_SHA=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
SOURCE_KIND='FRESH_RECORDED_VIDEO_OBSERVATION'


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def binding(observation):return digest({k:v for k,v in observation.items() if k!='recorded_geometry'})
def finite(value):return type(value) in (int,float) and math.isfinite(value)
def sha(value):return isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def box_valid(box):
    return (isinstance(box,dict) and all(finite(box.get(k)) for k in ('x','y','width','height'))
        and box['x']>=0 and box['y']>=0 and box['width']>0 and box['height']>0
        and box['x']+box['width']<=1 and box['y']+box['height']<=1)


def colour_roi_visible(box):
    # Includes every fixed placement-sensitivity offset used by measure_triplet.
    return (box_valid(box) and box['x']*640<=295 and (box['x']+box['width'])*640>=329
        and box['y']*480<=366 and (box['y']+box['height'])*480>=398)


def build_report(observation,frames,colour_checks,source_sha):
    first=observation['source_episode_intervals'][0]['start'][0]
    arrival=observation.get('timing_refinement',{}).get('arrival_reference',{}).get('actual_seconds')
    lower=arrival if finite(arrival) and arrival<=first else max(0,first-2.4)
    departure=observation.get('departure_interval_seconds')
    upper=departure[0] if departure else max(observation.get('sample_actual_seconds') or [first])
    evidence=[]
    for f in frames:
        if not lower-1e-6<=f['captured_at']<upper:continue
        evidence.append({'captured_at':f['captured_at'],'frame_id':f['frame_id'],'sha256':f['sha256'],
            'detections':[{k:deepcopy(d[k]) for k in ('position','track_id','status','box')} for d in f['detections']],
            'issues':deepcopy(f['issues']),'identity_events':deepcopy(f.get('identity_events',[]))})
    return {'policy_version':VERSION,'policy_sha256':POLICY_SHA,'tracker_version':TRACKER_VERSION,
        'tracker_sha256':IMPLEMENTATION_SHA,'source_sha256':source_sha,'observation_sha256':binding(observation),
        'frames':evidence,'colour_checks':deepcopy(colour_checks),'numeric_surface_used':False,'batch_identity_conflict':False,
        'scope':'RECORDED_FIXED_STATION_DEVELOPMENT_ONLY'}


def evaluate(observation):
    report=observation.get('recorded_geometry')
    if report is None and observation.get('source_kind')!=SOURCE_KIND:return None
    reasons=[];identity=None;recoveries=[];gaps=[]
    def result():
        return {'policy_version':VERSION,'status':'HELD' if reasons else 'SUPPORTED_WITH_RECOVERY' if gaps else 'SUPPORTED',
            'hold_reasons':sorted(set(reasons)),'track_id':identity,'supported_recoveries':recoveries,
            'unconfirmed_spans':gaps,'numeric_surface_used':False,'scope':'RECORDED_FIXED_STATION_DEVELOPMENT_ONLY',
            'evidence_sha256':digest(report) if isinstance(report,dict) else None}
    if not isinstance(report,dict):reasons.append('TRACKING_EVIDENCE_MISSING');return result()
    try:
        if report.get('policy_version')!=VERSION or report.get('policy_sha256')!=POLICY_SHA:reasons.append('TRACKING_POLICY_REVISION_MISMATCH')
        if report.get('tracker_version')!=TRACKER_VERSION or report.get('tracker_sha256')!=IMPLEMENTATION_SHA:reasons.append('TRACKING_DETECTOR_REVISION_MISMATCH')
        if report.get('source_sha256')!=observation['source_lineage']['video_sha256']:reasons.append('TRACKING_SOURCE_MISMATCH')
        if report.get('observation_sha256')!=binding(observation):reasons.append('TRACKING_OBSERVATION_BINDING_MISMATCH')
        if report.get('batch_identity_conflict'):reasons.append('TRACKING_ID_REUSED_ACROSS_FILLS')
        if report.get('numeric_surface_used') is not False:reasons.append('TRACKING_NUMERIC_SURFACE_NOT_ALLOWED')
        frames=report['frames'];times=[f['captured_at'] for f in frames]
        if not frames or any(not finite(t) for t in times) or any(b<=a for a,b in zip(times,times[1:])):
            reasons.append('TRACKING_FRAME_TIMES_INVALID');return result()
        if any(not sha(f['sha256']) or not isinstance(f['frame_id'],str) for f in frames):reasons.append('TRACKING_PIXEL_PROVENANCE_MISSING')
        samples=observation.get('sample_actual_seconds',[])
        if len(samples)!=3 or any(not finite(t) for t in samples):reasons.append('TRACKING_COLOUR_TIMES_MISSING');return result()
        first=observation['source_episode_intervals'][0]['start'][0];last=max(samples)
        tracks=[]
        for f in frames:
            if any(d.get('status') not in ('TRACKING','MOVING','CONFIRMING') or not box_valid(d.get('box')) for d in f['detections']):reasons.append('TRACKING_FRAME_STATE_INVALID')
            ds=[d for d in f['detections'] if d['position']=='Filling Position' and d['status']=='TRACKING' and isinstance(d['track_id'],str) and d['track_id'] and box_valid(d['box'])]
            if len(ds)>1:reasons.append('TRACKING_MULTIPLE_ACTIVE_VIALS')
            tracks.append(ds[0]['track_id'] if len(ds)==1 else None)
        before=[i for i,t in enumerate(times) if t<=first+1e-6 and tracks[i]]
        after=[i for i,t in enumerate(times) if t>=last-1e-6 and tracks[i]]
        if not before or first-times[before[-1]]>2.0+1e-6:reasons.append('TRACKING_PREFLOW_IDENTITY_UNCONFIRMED')
        if not after or times[after[0]]-last>2.0+1e-6:reasons.append('TRACKING_FINAL_IDENTITY_UNCONFIRMED')
        if not before or not after:return result()
        lo,hi=before[-1],after[0]
        ids={t for t in tracks[lo:hi+1] if t}
        if len(ids)!=1:reasons.append('TRACKING_IDENTITY_CHANGED')
        else:identity=next(iter(ids))
        if any(b-a>CONFIG['maximum_gap_seconds']+1e-6 for a,b in zip(times[lo:hi+1],times[lo+1:hi+1])):reasons.append('TRACKING_CAPTURE_GAP')
        for f in frames[lo:hi+1]:
            if f['issues'] and any(v!='NO_SUPPORTED_VIAL_GEOMETRY' for v in f['issues']):reasons.append('TRACKING_SOURCE_ISSUE')
            for event in f['identity_events']:
                if event['event']=='DETECTION_LOSS_IDENTITY_RESET':reasons.append('TRACKING_UNRESOLVED_IDENTITY_RESET')
                if event['event']=='DETECTION_LOSS_REASSOCIATED':
                    start=event.get('gap_started_at');end=event.get('recovered_at')
                    valid=(event.get('track_id')==identity and finite(start) and finite(end) and finite(event.get('duration_seconds'))
                        and 0<=event['duration_seconds']<=2.0+1e-6 and abs(end-f['captured_at'])<=1e-6
                        and abs(end-start-event['duration_seconds'])<=1e-6)
                    lost=[g['captured_at'] for g in frames if finite(start) and finite(end) and start-1e-6<=g['captured_at']<end and not g['detections']]
                    valid=valid and bool(lost) and event.get('interrupted_samples')==len(lost) and abs(min(lost)-start)<=1e-6 and abs(max(lost)-event.get('last_missing_at',-1))<=1e-6
                    if not valid:reasons.append('TRACKING_RECOVERY_INVALID')
                    recoveries.append(deepcopy(event))
        i=lo
        while i<=hi:
            if tracks[i]:i+=1;continue
            begin=i
            while i<=hi and not tracks[i]:i+=1
            end=i
            if begin==lo or end>hi or tracks[begin-1]!=tracks[end] or times[end]-times[begin]>2.0+1e-6:
                reasons.append('TRACKING_RECOVERY_UNRESOLVED')
            for j in range(begin,end):
                if frames[j]['detections']:continue
                pending=any(e['event']=='DETECTION_LOSS_PENDING' and e.get('track_id')==identity for e in frames[j]['identity_events'])
                resolved=any(e.get('track_id')==identity and finite(e.get('gap_started_at')) and finite(e.get('recovered_at')) and e['gap_started_at']-1e-6<=times[j]<e['recovered_at'] for e in recoveries)
                if not pending or not resolved:reasons.append('TRACKING_RECOVERY_PROVENANCE_MISSING')
            gaps.append({'start':times[begin],'resolved_at':times[end] if end<=hi else None,'samples':end-begin})
        checks=report['colour_checks'];provenance=observation['source_lineage'].get('frame_provenance',[])
        if len(checks)!=3 or len(provenance)!=3:reasons.append('TRACKING_COLOUR_EVIDENCE_MISSING')
        else:
            for t,check,p in zip(samples,checks,provenance):
                if (not finite(check.get('actual_seconds')) or abs(check['actual_seconds']-t)>1e-6
                    or check.get('sha256')!=p.get('sha256') or check.get('frame_id')!=p.get('evidence_id') or not sha(check.get('sha256'))):reasons.append('TRACKING_COLOUR_PROVENANCE_MISMATCH')
                if check.get('dimensions')!=[640,480] or not colour_roi_visible(check.get('box')):reasons.append('TRACKING_FINAL_COLOUR_VISIBILITY_UNCONFIRMED')
                # The direct sample box must agree with a nearby confirmed anchor.
                anchors=[j for j in range(lo,hi+1) if tracks[j]==identity and abs(times[j]-t)<=2.0+1e-6]
                if not anchors:reasons.append('TRACKING_COLOUR_IDENTITY_UNCONFIRMED')
                elif box_valid(check.get('box')):
                    j=min(anchors,key=lambda j:abs(times[j]-t));anchor=next(d['box'] for d in frames[j]['detections'] if d.get('track_id')==identity)
                    if max(abs(check['box'][k]-anchor[k]) for k in ('x','width'))>=.04:reasons.append('TRACKING_COLOUR_GEOMETRY_CHANGED')
    except (KeyError,TypeError,ValueError,IndexError):reasons.append('TRACKING_EVIDENCE_INVALID')
    return result()
