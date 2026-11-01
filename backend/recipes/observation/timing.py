"""Bounded timing proposals; conservative acceptance never uses recipe identity."""
import math

CONFIRM=.25
MAX_GAP=.05

def state(score):return 'FLOW' if score>=.5 else 'LOW_TRACE' if score<.25 else 'UNCERTAIN'

def analyze(records,kind):
 if len(records)<2:return {'status':'UNRESOLVED','reason':'INSUFFICIENT_CONTEXT','candidate_interval':None}
 times=[r['seconds'] for r in records]
 if any(not math.isfinite(t) for t in times) or any(b<=a or b-a>MAX_GAP+1e-9 for a,b in zip(times,times[1:])):
  return {'status':'UNRESOLVED','reason':'MISSING_DUPLICATE_OR_INVALID_FRAME_TIME','candidate_interval':None}
 if any(not math.isfinite(r['score']) or not 0<=r['score']<=1 for r in records):
  return {'status':'UNRESOLVED','reason':'INVALID_SCORE','candidate_interval':None}
 runs=[]
 for r in records:
  s=state(r['score'])
  if runs and runs[-1]['state']==s:runs[-1]['end']=r['seconds'];runs[-1]['frames']+=1
  else:runs.append({'state':s,'start':r['seconds'],'end':r['seconds'],'frames':1})
 # A brief full low-trace interval inside positive flow is retained as possible
 # pause evidence, never bridged to improve a confirmation percentage.
 short=[]
 for i,r in enumerate(runs):
  if r['state']=='LOW_TRACE' and r['end']-r['start']<CONFIRM-1e-9 and i and i+1<len(runs) and runs[i-1]['state']==runs[i+1]['state']=='FLOW':
   short.append([r['start'],r['end']])
 base={'runs':runs,'short_low_trace_gaps':short,'candidate_interval':None,
  'scope':'CONNECTED_TRACE_DIAGNOSTIC_NOT_DELIVERY_OR_IDENTITY_QUALIFICATION'}
 if kind in ('visibility','nonflow'):
  return {**base,'status':'DIAGNOSTIC_ONLY','reason':'ALL_CONNECTED_FLOW' if all(r['state']=='FLOW' for r in runs) else 'LOW_OR_UNCERTAIN_TRACE_REMAINS',
   'confirmed_trace_flow_runs':sum(r['state']=='FLOW' and r['end']-r['start']>=CONFIRM-1e-9 for r in runs)}
 if short:return {**base,'status':'UNRESOLVED','reason':'POSSIBLE_SHORT_PAUSE_DO_NOT_MERGE'}
 source,target=('LOW_TRACE','FLOW') if kind=='start' else ('FLOW','LOW_TRACE')
 candidates=[];previous=None
 for r in runs:
  if r['end']-r['start']<CONFIRM-1e-9:continue
  if r['state']==target and previous and previous['state']==source:
   candidates.append({'interval':[previous['end'],r['start']],'confirmation_seconds':r['start']+CONFIRM,
       'observed_confirmation_seconds':next(t for t in times if t>=r['start']+CONFIRM-1e-9)})
  if r['state']!='UNCERTAIN':previous=r
 if len(candidates)!=1:return {**base,'status':'UNRESOLVED','reason':'NO_UNIQUE_CONFIRMED_TRACE_TRANSITION','candidates':candidates}
 c=candidates[0]
 return {**base,'status':'TRACE_BOUNDARY_CANDIDATE','reason':'OPPOSING_TRACE_RUNS_CONFIRMED',
  'candidate_interval':c['interval'],'confirmation_seconds':c['observed_confirmation_seconds']}


VERSION = 'contained-native-boundaries/1'
LIMITS = {'history_seconds': .75, 'forward_seconds': 2.0,
          'maximum_visit_seconds': 30.0, 'maximum_video_seconds': 300.0,
          'confirmation_seconds': CONFIRM, 'maximum_gap_seconds': MAX_GAP}


def accept_visit(visit, diagnostics):
    """All boundaries must narrow their originals. No partial or identity-led fit."""
    from copy import deepcopy
    original = deepcopy(visit['episodes'])
    result = {'version': VERSION, 'status': 'BASELINE_RETAINED',
              'baseline_episode_intervals': original, 'boundaries': diagnostics,
              'original_flags_retained': list(visit['flags']), 'limits': dict(LIMITS)}
    if visit['flags']:
        return original, {**result, 'reason': 'EXISTING_OBSERVATION_HOLD'}
    expected = {(e['order'], kind) for e in original for kind in ('start', 'end')}
    actual = [(r['order'], r['kind']) for r in diagnostics]
    if len(actual) != len(expected) or set(actual) != expected:
        return original, {**result, 'reason': 'INCOMPLETE_BOUNDARY_COVERAGE'}
    proposals = deepcopy(original)
    for r in diagnostics:
        if r['diagnostic']['status'] != 'TRACE_BOUNDARY_CANDIDATE':
            return original, {**result, 'reason': 'UNRESOLVED_NATIVE_BOUNDARY'}
        proposed = r['diagnostic']['candidate_interval']
        key = r['kind'] + '_interval_seconds'
        before = original[r['order']-1][key]
        if before is None or not (before[0] <= proposed[0] <= proposed[1] <= before[1]):
            return original, {**result, 'reason': 'CANDIDATE_OUTSIDE_BASELINE_INTERVAL'}
        proposals[r['order']-1][key] = list(proposed)
    if any(e['end_interval_seconds'] is None or e['start_interval_seconds'][1] >= e['end_interval_seconds'][0] for e in proposals):
        return original, {**result, 'reason': 'INVALID_REFINED_DURATION'}
    if any(a['end_interval_seconds'][1] >= b['start_interval_seconds'][0] for a,b in zip(proposals,proposals[1:])):
        return original, {**result, 'reason': 'INVALID_REFINED_EPISODE_ORDER'}
    return proposals, {**result, 'status': 'REFINED', 'reason': 'ALL_BOUNDARIES_CONTAINED_AND_CONFIRMED',
                       'appearance_window_retained_from_baseline': True}
