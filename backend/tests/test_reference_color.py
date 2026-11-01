"""Reference qualification and recorded discovery regression checks."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from tempfile import TemporaryDirectory
from recipes.reference_color import qualified_color,rejection_reasons
from recipes.demo_store import DemoBank
from recorded_tracking_fixtures import with_tracking
REPO=Path(__file__).resolve().parents[2]

def run_bank(observations,profiles,rules,catalog_ids,variant):
 with TemporaryDirectory() as tmp:
  bank=DemoBank(Path(tmp)/'demo.sqlite3',profiles,rules,catalog_ids,
   normal_paths=[Path(tmp)/'normal.sqlite3'],bundle_revision='guard-unit-tests',allow_development_writes=True)
  try:return {**bank.assess_many(observations),'counts':bank.counts()}
  finally:bank.close()

def source_fixture():
 bundle=json.loads((REPO/'backend/recipe_demo_assets/recorded_observations.json').read_text())
 return deepcopy(next(o for o in bundle['observations'] if o['vial_id']=='V1-V06'))
from recipes.reviewed_trial import compare_color,compare_timing

BUNDLE=json.loads((REPO/'backend/recipe_trial_assets/reviewed_trial.json').read_text())
RULES=BUNDLE['rules']

def profile(uid='good',rid=7,rgb=None,temporal=0,spatial=0):
 return {'vial_uid':uid,'recipe_id':rid,'duration_bounds_s':[[10,11]],
  'raw_rgb':{'nominal':[100,100,100] if rgb is None else rgb,'temporal_distance':temporal,'region_distance':spatial}}

def query():return {'raw_rgb':{'nominal':[100,100,100],'temporal_distance':0,'region_distance':0},'phase_note':'synthetic test'}

class ReferenceQualityTests(unittest.TestCase):
 def test_exact_approved_limits_remain_eligible(self):
  p=profile(temporal=RULES['temporal_distance_limit'],spatial=RULES['placement_distance_limit'])
  self.assertEqual(rejection_reasons(p,RULES),[])
  self.assertEqual(qualified_color(query(),[7],[p],RULES)['status'],'CONSISTENT')

 def test_temporally_unstable_nearest_color_cannot_support_match(self):
  profiles=[profile('unstable',temporal=12),profile('stable',rgb=[0,0,0])]
  self.assertEqual(compare_color(query(),[7],profiles,RULES)['status'],'CONSISTENT')
  result=qualified_color(query(),[7],profiles,RULES)
  self.assertEqual(result['status'],'CONFLICTING');self.assertGreater(result['comparisons'][0]['color_distance'],24.1)

 def test_spatially_unstable_color_cannot_provide_contradiction(self):
  result=qualified_color(query(),[7],[profile(rgb=[0,0,0],spatial=3)],RULES)
  self.assertEqual(result['status'],'UNRELIABLE');self.assertEqual(result['comparisons'],[])

 def test_one_good_reference_same_id_still_supports_comparison(self):
  result=qualified_color(query(),[7],[profile('bad',temporal=12),profile('good')],RULES)
  self.assertEqual(result['status'],'CONSISTENT');self.assertEqual(result['reference_color_qualification']['qualified_profile_count'],1)

 def test_missing_color_is_unreliable(self):
  p=profile();p['raw_rgb']=None
  result=qualified_color(query(),[7],[p],RULES)
  self.assertEqual(result['status'],'UNRELIABLE');self.assertEqual(result['reference_color_qualification']['missing_qualified_color_recipe_ids'],[7])

 def test_invalid_or_missing_reference_metrics_are_withheld(self):
  for value in [None,-1,float('nan'),float('inf'),True,'0']:
   with self.subTest(value=value):
    p=profile();p['raw_rgb']['temporal_distance']=value
    self.assertEqual(qualified_color(query(),[7],[p],RULES)['status'],'UNRELIABLE')
  p=profile();del p['raw_rgb']['region_distance']
  self.assertTrue(rejection_reasons(p,RULES))

 def test_invalid_rgb_is_withheld(self):
  for rgb in [[100,100],[-1,0,0],[256,0,0],[float('nan'),0,0],[True,0,0]]:
   self.assertEqual(qualified_color(query(),[7],[profile(rgb=rgb)],RULES)['status'],'UNRELIABLE')

 def test_no_reference_removal_from_timing_or_ambiguous_ids(self):
  profiles=[profile('bad',rid=7,spatial=3),profile('good',rid=8)]
  before=compare_timing([[10,11]],profiles,1)
  result=qualified_color(query(),before['possible_recipe_ids'],profiles,RULES)
  self.assertEqual(before['status'],'AMBIGUOUS');self.assertEqual(before['possible_recipe_ids'],[7,8])
  self.assertEqual(result['status'],'UNRELIABLE');self.assertEqual(compare_timing([[10,11]],profiles,1),before)

 def test_unreliable_query_stays_unreliable_with_good_reference(self):
  q=query();q['raw_rgb']['temporal_distance']=3
  self.assertEqual(qualified_color(q,[7],[profile()],RULES)['status'],'UNRELIABLE')

 def test_inputs_are_immutable(self):
  profiles=[profile(spatial=3)];q=query();before=deepcopy((profiles,q,RULES))
  qualified_color(q,[7],profiles,RULES)
  self.assertEqual((profiles,q,RULES),before)

 def test_no_timing_candidate_still_allows_existing_discovery_path(self):
  o=with_tracking(source_fixture())
  result=run_bank([o],[],RULES,{7},True)
  self.assertEqual(result['results'][0]['assessment']['action'],'CREATE_DISCOVERED_PATTERN')

 def test_timing_match_with_no_qualified_color_cannot_create_or_reuse_id(self):
  o=with_tracking(source_fixture())
  p=profile(temporal=12);p['duration_bounds_s']=o['duration_bounds_seconds'];p['raw_rgb']['nominal']=o['raw_rgb']['nominal']
  result=run_bank([o],[p],RULES,{7},True)
  a=result['results'][0]['assessment'];self.assertEqual(a['timing']['possible_recipe_ids'],[7])
  self.assertEqual(a['action'],'UNRESOLVED');self.assertIsNone(a['recipe_id'])
  self.assertEqual(a['reason'],'REFERENCE_COMPARISON_UNRELIABLE')
  self.assertEqual(result['counts']['discovered_patterns'],0);self.assertEqual(result['counts']['linked_occurrences'],0)


class VersionedGuardStoreTests(unittest.TestCase):
 def test_old_engine_store_is_not_silently_reinterpreted(self):
  from unittest.mock import patch
  with TemporaryDirectory() as tmp:
   path=Path(tmp)/'bank.sqlite3'
   kwargs={'normal_paths':[Path(tmp)/'normal.sqlite3'],'bundle_revision':'same-inputs','allow_development_writes':True}
   with patch('recipes.demo_store.ENGINE_VERSION','recorded-pattern-demo/1.0'):
    old=DemoBank(path,[],RULES,{7},**kwargs)
    old.assess(source_fixture());old.close()
   with self.assertRaisesRegex(ValueError,'revision differs'):
    DemoBank(path,[],RULES,{7},**kwargs)
   # The original version can still read its unchanged records.
   with patch('recipes.demo_store.ENGINE_VERSION','recorded-pattern-demo/1.0'):
    original=DemoBank(path,[],RULES,{7},**kwargs)
    try:self.assertEqual(original.counts()['saved_assessments'],1)
    finally:original.close()

if __name__=='__main__':unittest.main()
