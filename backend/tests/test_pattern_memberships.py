from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from recipes.demo_store import DemoBank
from recipes.workflow_api import load_reference_catalog

BUNDLE=json.loads((Path(__file__).parents[1]/'recipe_trial_assets/reviewed_trial.json').read_text())
FIXTURE=json.loads((Path(__file__).parent/'fixtures/two_fill_observations.json').read_text())
CATALOG,_=load_reference_catalog()


def observation(label):return deepcopy(next(o for o in FIXTURE['observations'] if o['label']==label))

def synthetic(number,rgb=None):
 o=observation('Video 1 · Vial 13');o['observation_id']=f'synthetic-repeat-{number}';o['label']=f'Synthetic Fill {number}'
 o['source_lineage']['video_sha256']=format(number,'064x')
 if rgb is not None:o['raw_rgb']['nominal']=rgb
 return o


class MembershipTests(unittest.TestCase):
 def setUp(self):
  self.folder=TemporaryDirectory();self.addCleanup(self.folder.cleanup);self.path=Path(self.folder.name)/'bank.sqlite3';self.banks=[];self.addCleanup(self.close)
  self.bank=self.open()
  for label in ['Video 1 · Vial 6','Video 1 · Vial 16']:self.bank.assess(observation(label))
 def close(self):
  for bank in self.banks:
   if bank.connection is not None:bank.close()
 def open(self):
  bank=DemoBank(self.path,BUNDLE['profiles'],BUNDLE['rules'],{int(i) for i in CATALOG['recipes']},
   normal_paths=[Path(self.folder.name)/'normal.sqlite3'],bundle_revision='membership-tests',allow_development_writes=True)
  self.banks.append(bank);return bank
 def assess(self,o):return self.bank.assess(o)['assessment']
 def pair(self):
  a=self.assess(observation('Video 1 · Vial 13'));b=self.assess(observation('Video 2 · Vial 3'));return a,b
 def test_second_distinct_fill_confirms_both_members_without_rewriting_baseline(self):
  a=self.assess(observation('Video 1 · Vial 13'));key=a['observation_key']
  original=self.bank.connection.execute('SELECT result FROM demo_assessments WHERE observation_key=?',(key,)).fetchone()[0]
  self.assertEqual(a['pattern_membership']['status'],'PENDING_REPEAT');self.assertIsNone(a['pattern_membership']['recipe_id'])
  b=self.assess(observation('Video 2 · Vial 3'));effective=next(a for a in self.bank.assessments() if a['observation_key']==key)
  self.assertEqual(b['pattern_membership']['recipe_id'],102);self.assertEqual(effective['pattern_membership']['recipe_id'],102)
  self.assertEqual(self.bank.connection.execute('SELECT result FROM demo_assessments WHERE observation_key=?',(key,)).fetchone()[0],original)
  self.assertIsNone(effective['recipe_id']);self.assertEqual(effective['timing']['possible_recipe_ids'],[7]);self.assertEqual(effective['color']['status'],'CONFLICTING')
  history=self.bank.membership_history(key);self.assertEqual([r['status'] for r in history],['PENDING_REPEAT','DISCOVERED_UNVERIFIED'])
  self.assertEqual(history[1]['supersedes_revision_id'],history[0]['revision_id'])
 def test_playback_snapshot_does_not_reveal_a_later_pattern_confirmation(self):
  from recipes.inspection_log import playback_events
  first=observation('Video 1 · Vial 13');second=observation('Video 2 · Vial 3')
  # Shift all temporal evidence of the second synthetic test observation forward,
  # so this tests snapshot causality without relying on recording-relative clocks.
  second['source_episode_intervals']=[{'start':[v+1000 for v in e['start']],'end':[v+1000 for v in e['end']]} for e in second['source_episode_intervals']]
  second['duration_bounds_seconds']=[[e['end'][0]-e['start'][1],e['end'][1]-e['start'][0]] for e in second['source_episode_intervals']]
  second['sample_actual_seconds']=[v+1000 for v in second['sample_actual_seconds']]
  second['departure_interval_seconds']=[v+1000 for v in second['departure_interval_seconds']]
  second['candidate_appearance_window_seconds']=[v+1000 for v in second['candidate_appearance_window_seconds']]
  result=self.bank.assess_many([first,second],capture_timeline=True)
  snapshots=result['playback_snapshots']
  initial=next(s for s in snapshots if s['initial'] and s['assessment']['observation_id']==first['observation_id'])
  self.assertEqual(initial['assessment']['pattern_membership']['status'],'PENDING_REPEAT')
  updated=next(s for s in snapshots if not s['initial'])
  self.assertEqual(updated['assessment']['pattern_membership']['status'],'DISCOVERED_UNVERIFIED')
  self.assertGreater(updated['at'],initial['at'])
  events=playback_events(snapshots)
  early=[e for e in events if e['at']<=initial['at'] and e['kind']=='recipe']
  self.assertTrue(all('102' not in e['title'] for e in early))

 def test_restart_persists_pending_confirmation_and_history(self):
  self.assess(observation('Video 1 · Vial 13'));self.bank=self.open()
  self.assertEqual(self.bank.pending_patterns()[0]['qualifying_fill_count'],1)
  self.assess(observation('Video 2 · Vial 3'));self.bank=self.open()
  self.assertEqual(self.bank.pending_patterns()[0]['recipe_id'],102)
  self.assertEqual(len(self.bank.assessments()[-2]['pattern_membership']['history']),2)
 def test_replay_and_alias_do_not_count_twice(self):
  o=observation('Video 1 · Vial 13');self.assess(o);self.assess(o)
  alias=deepcopy(o);alias['observation_id']='another-producer-name'
  r=self.assess(alias);self.assertEqual(r['pattern_membership']['status'],'DUPLICATE_FILL_NOT_COUNTED')
  self.assertEqual(self.bank.pending_patterns()[0]['qualifying_fill_count'],1);self.assertEqual(len(self.bank.patterns()),2)
 def test_changed_same_identity_evidence_is_rejected(self):
  o=synthetic(1);self.assess(o);o['raw_rgb']['nominal']=[12,12,12]
  with self.assertRaises(ValueError):self.assess(o)
 def test_existing_holds_and_missing_reference_color_still_block(self):
  for label in ['Video 1 · Vial 11','Video 1 · Vial 17','Video 1 · Vial 8','Video 1 · Vial 18','Video 1 · Vial 10']:
   self.assertNotIn('pattern_membership',self.assess(observation(label)))
  for p in self.bank.references:
   if p['recipe_id']==7:p['raw_rgb']=None
  self.assertNotIn('pattern_membership',self.assess(observation('Video 1 · Vial 13')))
  self.assertEqual(self.bank.pending_patterns(),[])
 def test_invalid_phase_and_missing_arrival_cannot_supply_repeat(self):
  a=synthetic(1);a['reference_cadence_and_window_check']=False
  self.assertNotIn('pattern_membership',self.assess(a))
  b=synthetic(2);b['timing_refinement'].pop('arrival_reference')
  self.assertNotIn('pattern_membership',self.assess(b))
 def test_third_qualifying_fill_reuses_confirmed_group_without_baseline_ambiguity(self):
  self.pair();r=self.assess(synthetic(3))
  self.assertEqual(r['timing']['possible_recipe_ids'],[7]);self.assertEqual(r['pattern_membership']['recipe_id'],102)
  self.assertEqual(r['pattern_membership']['event'],'PATTERN_REUSED')
  self.assertEqual(self.bank.pending_patterns()[0]['qualifying_fill_count'],3)
  self.assertEqual(next(p for p in self.bank.patterns() if p['recipe_id']==102)['occurrence_count'],3)
 def test_color_groups_do_not_average_or_chain(self):
  self.assess(synthetic(1,[50,10,10]));self.assess(synthetic(2,[70,10,10]))
  r=self.assess(synthetic(3,[30,10,10]))
  self.assertEqual(r['pattern_membership']['status'],'AMBIGUOUS_PATTERN');self.assertEqual(len(self.bank.pending_patterns()),1)
  self.assertEqual(self.bank.pending_patterns()[0]['qualifying_fill_count'],2)
 def test_batch_rollback_includes_groups_revisions_and_occurrences(self):
  self.assess(observation('Video 1 · Vial 13'));before=self.bank.counts();history=self.bank.pending_patterns()
  with self.assertRaises(ValueError):self.bank.assess_many([observation('Video 2 · Vial 3'),{'observation_id':'invalid'}])
  self.assertEqual(self.bank.counts(),before);self.assertEqual(self.bank.pending_patterns(),history)
 def test_concurrent_repeat_is_serialized_across_connections(self):
  self.assess(observation('Video 1 · Vial 13'));other=self.open();o=observation('Video 2 · Vial 3')
  with ThreadPoolExecutor(max_workers=2) as pool:
   replies=list(pool.map(lambda b:b.assess(o),[self.bank,other]))
  self.assertEqual(sum(r['idempotent_replay'] for r in replies),1)
  self.assertEqual(self.bank.pending_patterns()[0]['qualifying_fill_count'],2)
  self.assertEqual(len(self.bank.patterns()),3)
 def test_full_recorded_stream_has_eight_effective_links_and_two_pending_groups(self):
  with TemporaryDirectory() as tmp:
   bank=DemoBank(Path(tmp)/'full.sqlite3',BUNDLE['profiles'],BUNDLE['rules'],{int(i) for i in CATALOG['recipes']},
    normal_paths=[Path(tmp)/'normal.sqlite3'],bundle_revision='whole-stream',allow_development_writes=True)
   try:
    result=bank.assess_many(FIXTURE['observations']);self.assertEqual(bank.counts()['linked_occurrences'],8)
    self.assertEqual(len(bank.patterns()),3);self.assertEqual(sum(g['status']=='PENDING_REPEAT' for g in bank.pending_patterns()),2)
    self.assertEqual(sum(a['recipe_id'] is not None for a in bank.baseline_assessments()),6)
    current=[r['assessment'] for r in result['results']]
    self.assertEqual(sum(a.get('pattern_membership',{}).get('recipe_id') is not None for a in current),2)
    self.assertEqual(bank.assess_many(FIXTURE['observations'])['new_patterns'],0)
   finally:bank.close()
 def test_older_bank_is_not_modified_by_new_membership_schema(self):
  with TemporaryDirectory() as tmp:
   path=Path(tmp)/'old.sqlite3';kwargs=dict(normal_paths=[],bundle_revision='old',allow_development_writes=True)
   with patch('recipes.demo_store.ENGINE_VERSION','recorded-pattern-demo/1.2'):
    old=DemoBank(path,[],BUNDLE['rules'],{99},**kwargs)
    for table in ['demo_membership_revisions','demo_group_members','demo_pending_groups']:old.connection.execute('DROP TABLE '+table)
    old.close()
   with self.assertRaises(ValueError):DemoBank(path,[],BUNDLE['rules'],{99},**kwargs)
   import sqlite3
   from contextlib import closing
   with closing(sqlite3.connect(path)) as connection:
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    self.assertNotIn('demo_pending_groups',names)

 def test_multiple_pending_matches_remain_ambiguous_without_a_vote(self):
  self.assess(synthetic(1,[50,10,10]));self.assess(synthetic(2,[90,10,10]))
  result=self.assess(synthetic(3,[70,10,10]))
  self.assertEqual(result['pattern_membership']['status'],'AMBIGUOUS_PATTERN')
  self.assertEqual([g['qualifying_fill_count'] for g in self.bank.pending_patterns()],[1,1])
  self.assertEqual(len(self.bank.patterns()),2)
 def test_pending_group_does_not_reserve_an_id_or_collide_with_ordinary_discovery(self):
  self.assess(observation('Video 1 · Vial 13'))
  o=synthetic(5);start=o['source_episode_intervals'][0]['start'][0]
  intervals=[{'start':[start,start],'end':[start+100,start+100.1]},
             {'start':[start+105,start+105],'end':[start+115,start+115.1]}]
  o['source_episode_intervals']=intervals;o['episodes']=deepcopy(intervals)
  o['duration_bounds_seconds']=[[e['end'][0]-e['start'][1],e['end'][1]-e['start'][0]] for e in intervals]
  o['candidate_appearance_window_seconds']=[start+116,start+119]
  o['sample_actual_seconds']=[start+116.05,start+116.15,start+116.25];o['departure_interval_seconds']=[start+120,start+120.25]
  ordinary=self.assess(o);self.assertEqual(ordinary['action'],'CREATE_DISCOVERED_PATTERN');self.assertEqual(ordinary['recipe_id'],102)
  repeated=self.assess(observation('Video 2 · Vial 3'));self.assertEqual(repeated['pattern_membership']['recipe_id'],103)

 def test_confirmed_pattern_is_reused_before_no_reference_discovery(self):
  self.pair();o=synthetic(4);start=o['source_episode_intervals'][0]['start'][0]
  intervals=[{'start':[start,start],'end':[start+13.4,start+13.5]},
             {'start':[start+16,start+16],'end':[start+17.3,start+17.4]}]
  o['source_episode_intervals']=intervals;o['episodes']=deepcopy(intervals)
  o['duration_bounds_seconds']=[[e['end'][0]-e['start'][1],e['end'][1]-e['start'][0]] for e in intervals]
  o['candidate_appearance_window_seconds']=[start+18,start+21]
  o['sample_actual_seconds']=[start+18.05,start+18.15,start+18.25];o['departure_interval_seconds']=[start+22,start+22.25]
  result=self.assess(o)
  self.assertEqual(result['timing']['status'],'NO_COMPATIBLE_REFERENCE')
  self.assertEqual(result['pattern_membership']['recipe_id'],102)
  self.assertEqual(result['reason'],'KNOWN_OBSERVED_PATTERN_REUSE')
  self.assertEqual(len(self.bank.patterns()),3)

if __name__=='__main__':unittest.main()


