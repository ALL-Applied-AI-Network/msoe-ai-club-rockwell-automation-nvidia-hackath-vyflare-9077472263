import unittest
from recipes.observation.timing import analyze

def records(parts):
 output=[];i=0
 for count,score in parts:
  for _ in range(count):output.append({'seconds':i/30,'score':score});i+=1
 return output

class CadenceTests(unittest.TestCase):
 def test_sustained_onset_and_stop(self):
  for kind,parts in [('start',[(15,0),(20,1)]),('end',[(15,1),(20,0)])]:
   r=analyze(records(parts),kind);self.assertEqual(r['status'],'TRACE_BOUNDARY_CANDIDATE')
   self.assertAlmostEqual(r['candidate_interval'][1]-r['candidate_interval'][0],1/30)
   self.assertGreaterEqual(r['confirmation_seconds']-r['candidate_interval'][1],.25)
 def test_hanging_drop_or_isolated_short_flow_does_not_start(self):
  for pulse in (1,2,3,6):
   self.assertEqual(analyze(records([(15,0),(pulse,1),(15,0)]),'start')['status'],'UNRESOLVED')
 def test_short_apparent_pauses_are_not_erased(self):
  for count in (4,7):
   r=analyze(records([(15,1),(count,0),(15,1)]),'end')
   self.assertEqual(r['reason'],'POSSIBLE_SHORT_PAUSE_DO_NOT_MERGE')
 def test_longer_pause_has_distinct_end_and_new_start(self):
  for count in (9,16,31):
   frames=records([(15,1),(count,0),(15,1)])
   end=analyze(frames,'end');start=analyze(frames,'start')
   self.assertEqual(end['status'],'TRACE_BOUNDARY_CANDIDATE');self.assertEqual(start['status'],'TRACE_BOUNDARY_CANDIDATE')
   self.assertLess(end['candidate_interval'][1],start['candidate_interval'][0])
 def test_weak_gap_inside_flow_is_not_qualified_by_return(self):
  r=analyze(records([(15,1),(5,.4),(15,1)]),'visibility')
  self.assertEqual(r['reason'],'LOW_OR_UNCERTAIN_TRACE_REMAINS')
 def test_missing_duplicate_and_nonfinite_times_fail(self):
  for change in ('missing','duplicate','nan'):
   rows=records([(15,0),(15,1)])
   if change=='missing':del rows[10]
   elif change=='duplicate':rows[10]['seconds']=rows[9]['seconds']
   else:rows[10]['seconds']=float('nan')
   self.assertEqual(analyze(rows,'start')['reason'],'MISSING_DUPLICATE_OR_INVALID_FRAME_TIME')
 def test_eof_startup_or_budget_clipping_does_not_confirm(self):
  for rows in (records([(20,1)]),records([(15,0),(3,1)]),records([(3,0),(15,1)])):
   self.assertEqual(analyze(rows,'start')['status'],'UNRESOLVED')
 def test_uncertain_transition_interval_is_retained(self):
  r=analyze(records([(15,0),(5,.4),(20,1)]),'start')
  self.assertGreater(r['candidate_interval'][1]-r['candidate_interval'][0],.15)
 def test_nonflow_control_does_not_invent_episode(self):
  r=analyze(records([(90,0)]),'nonflow');self.assertEqual(r['confirmed_trace_flow_runs'],0)
 def test_same_ordered_evidence_produces_same_result(self):
  rows=records([(15,0),(20,1)]);parts=rows[:10]+rows[10:20]+rows[20:]
  self.assertEqual(analyze(rows,'start'),analyze(parts,'start'))




from copy import deepcopy
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch
from recipes.observation.timing import accept_visit
from recipes.observation.refine import refine_visits, plan

def visit(flags=None):
 return {'first_stationary_seconds':0,'last_stationary_seconds':9,
  'departure_interval_seconds':[9,9.25], 'flags':flags or [],
  'candidate_appearance_window_seconds':[5,8.75],
  'episodes':[{'order':1,'start_interval_seconds':[1,1.25],'end_interval_seconds':[4,4.25],
               'end_confirmed':True,'evidence_frame_ids':['old-start','old-end']}]}

def diagnostics():
 return [{'order':1,'kind':kind,'diagnostic':{'status':'TRACE_BOUNDARY_CANDIDATE',
  'candidate_interval':interval}} for kind,interval in [('start',[1.1,1.2]),('end',[4.1,4.2])]]

class AcceptanceTests(unittest.TestCase):
 def test_only_complete_contained_refinements_are_accepted(self):
  v=visit();before=deepcopy(v);episodes,meta=accept_visit(v,diagnostics())
  self.assertEqual(meta['status'],'REFINED');self.assertEqual(episodes[0]['start_interval_seconds'],[1.1,1.2])
  self.assertEqual(v,before);self.assertEqual(v['candidate_appearance_window_seconds'],[5,8.75])
 def test_shifted_candidate_preserves_whole_baseline(self):
  d=diagnostics();d[0]['diagnostic']['candidate_interval']=[.9,1.2]
  v=visit();episodes,meta=accept_visit(v,d)
  self.assertEqual(episodes,v['episodes']);self.assertEqual(meta['reason'],'CANDIDATE_OUTSIDE_BASELINE_INTERVAL')
 def test_partial_duplicate_or_unresolved_coverage_never_partly_updates(self):
  d=diagnostics();bad=deepcopy(d);bad[1]['diagnostic']['status']='UNRESOLVED'
  for evidence in (d[:1],[d[0],d[0]],bad):
   v=visit();episodes,meta=accept_visit(v,evidence)
   self.assertEqual(episodes,v['episodes']);self.assertEqual(meta['status'],'BASELINE_RETAINED')
 def test_arrival_and_flow_holds_are_not_cleared(self):
  for flag in ('ARRIVAL_LEFT_CENSORED','UNRESOLVED_FLOW_VISIBILITY'):
   v=visit([flag]);episodes,meta=accept_visit(v,diagnostics())
   self.assertEqual(episodes,v['episodes']);self.assertEqual(meta['reason'],'EXISTING_OBSERVATION_HOLD')
   self.assertEqual(meta['original_flags_retained'],[flag])
 def test_native_decoder_failure_falls_back_without_mutating_source(self):
  v=visit();before=deepcopy(v)
  class Broken:
   def decode(self,*args):raise ValueError('synthetic invalid decoder output')
  with TemporaryDirectory() as tmp,self.assertLogs(level='WARNING'):
   out=refine_visits([v],[],Path(tmp),Broken(),'source',Path(tmp)/'native',{})
  self.assertEqual(out[0]['episodes'],v['episodes']);self.assertEqual(v,before)
  self.assertEqual(out[0]['timing_refinement']['reason'],'NATIVE_REVIEW_UNAVAILABLE')
 def test_missing_window_evidence_falls_back(self):
  class Missing:
   def decode(self,*args):return []
  with TemporaryDirectory() as tmp,self.assertLogs(level='WARNING'):
   out=refine_visits([visit()],[],Path(tmp),Missing(),'source',Path(tmp)/'native',{})
  self.assertEqual(out[0]['timing_refinement']['reason'],'NATIVE_REVIEW_UNAVAILABLE')
 def test_missing_arrival_reference_is_a_fallback(self):
  v=visit();windows,_,_=plan([v])
  class Decoder:
   def decode(self,*args):return [{'id':w['id']+'_0000','actual_seconds':w['lower']} for w in windows]
  with TemporaryDirectory() as tmp:
   out=refine_visits([v],[],Path(tmp),Decoder(),'source',Path(tmp)/'native',{})
  self.assertEqual(out[0]['timing_refinement']['reason'],'NATIVE_VISIT_EVIDENCE_INVALID')
 def test_single_frame_low_trace_inside_flow_remains_uncertain(self):
  self.assertEqual(analyze(records([(15,1),(1,0),(15,1)]),'end')['reason'],'POSSIBLE_SHORT_PAUSE_DO_NOT_MERGE')
 def test_resource_cap_leaves_later_visits_on_baseline(self):
  source=[]
  for i in range(120):
   v=visit();offset=i*15
   v['first_stationary_seconds']+=offset;v['departure_interval_seconds']=[9+offset,9.25+offset]
   for episode in v['episodes']:
    for key in ('start_interval_seconds','end_interval_seconds'):episode[key]=[t+offset for t in episode[key]]
   source.append(v)
  windows,jobs,fallback=plan(source)
  self.assertLessEqual(sum(w['upper']-w['lower'] for w in windows),300)
  self.assertTrue(fallback);self.assertTrue(all(m['reason']=='NATIVE_REVIEW_RESOURCE_LIMIT' for m in fallback.values()))
  self.assertEqual(len(jobs)+len(fallback),120)

if __name__=='__main__':unittest.main()
