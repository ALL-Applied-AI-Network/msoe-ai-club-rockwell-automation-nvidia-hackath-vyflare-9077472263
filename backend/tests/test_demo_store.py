"""Workflow/transaction tests using explicit synthetic observation fixtures."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from recipes.demo_store import DemoBank
HERE=Path(__file__).resolve().parent

RULES={"timing_allowance_seconds":1.0,"color_distance_limit":24.10,"temporal_distance_limit":2.24,"placement_distance_limit":2.45}
REFERENCES=[{"recipe_id":7,"vial_uid":"synthetic-reference-7","duration_bounds_s":[[3,3.2],[1,1.2]],"raw_rgb":{"nominal":[100,40,20],"temporal_distance":0,"region_distance":0}}]
NOMINAL=set(range(1,100))


def observation(uid,bounds=((30,30.1),(3,3.1)),rgb=(30,60,80)):
    intervals=[];clock=1.0
    for lo,hi in bounds:
        intervals.append({"start":[clock,clock],"end":[clock+lo,clock+hi]});clock+=hi+2
    end=intervals[-1]["end"][1]
    return {"observation_id":uid,"source_kind":"SYNTHETIC_WORKFLOW_FIXTURE_NOT_VIDEO_EVIDENCE",
        "duration_bounds_seconds":[[e["end"][0]-e["start"][1],e["end"][1]-e["start"][0]] for e in intervals],
        "source_episode_intervals":intervals,"raw_rgb":{"nominal":list(rgb),"temporal_distance":0,"region_distance":0},
        "sample_actual_seconds":[end+1.05,end+1.15,end+1.25],"departure_interval_seconds":[end+5,end+5.25],
        "candidate_appearance_window_seconds":[end+.5,end+4.5],"reference_cadence_and_window_check":True,
        "available_demo_checks_pass":True,"hold_reasons":[],"operational_eligibility":"SYNTHETIC_FIXTURE_ONLY",
        "source_lineage":{"video_sha256":"a"*64},"dispense_colors":None,"tank_sources":None}


class BankTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(dir=HERE)
        self.path=Path(self.folder.name)/"test.sqlite3"
        self.bank=self.open()
    def tearDown(self):
        self.bank.close();self.folder.cleanup()
    def open(self,refs=REFERENCES):return DemoBank(self.path,refs,RULES,NOMINAL,
        normal_paths=[PROJECT_BANK],bundle_revision="synthetic-store-tests/1",allow_development_writes=True)
    def assess(self,o):return self.bank.assess(o)["assessment"]

    def test_known_pattern_reuses_existing_id(self):
        r=self.assess(observation("known",((3,3.1),(1,1.1)),(100,40,20)))
        self.assertEqual(r["action"],"REUSE_REFERENCE_PATTERN");self.assertEqual(r["recipe_id"],7)
        self.assertIsNone(r["confirmed_nominal_recipe_id"])
        self.assertEqual(self.bank.patterns(),[])

    def test_unknown_creates_unverified_entry_despite_missing_nominal_coverage(self):
        o=observation("new");r=self.assess(o)
        self.assertEqual(r["action"],"CREATE_DISCOVERED_PATTERN");self.assertEqual(r["recipe_id"],100)
        self.assertEqual(self.bank.patterns()[0]["status"],"DISCOVERED_UNVERIFIED")
        self.assertEqual(self.bank.patterns()[0]["profile"]["duration_bounds_s"],o["duration_bounds_seconds"])
        self.assertIsNone(o["dispense_colors"])

    def test_repeat_reuses_id_without_changing_founder(self):
        first=self.assess(observation("first"));before=deepcopy(self.bank.patterns()[0]["profile"])
        repeat=self.assess(observation("repeat",((30.1,30.2),(3.1,3.2))))
        self.assertEqual(repeat["action"],"REUSE_DISCOVERED_PATTERN")
        self.assertEqual(first["recipe_id"],repeat["recipe_id"])
        self.assertEqual(self.bank.patterns()[0]["profile"],before)
        self.assertEqual(self.bank.patterns()[0]["occurrence_count"],2)

    def test_distinct_pattern_creates_another_id(self):
        a=self.assess(observation("first"));b=self.assess(observation("different",((45,45.1),(8,8.1))))
        self.assertNotEqual(a["recipe_id"],b["recipe_id"]);self.assertEqual(len(self.bank.patterns()),2)

    def test_unreliable_observation_does_not_create(self):
        o=observation("bad");o["raw_rgb"]["region_distance"]=3
        r=self.assess(o);self.assertEqual(r["action"],"UNRESOLVED");self.assertEqual(self.bank.patterns(),[])

    def test_boundary_case_stays_unresolved_as_user_requested(self):
        o=observation("boundary",((2,4.5),(1,1.2)),(100,40,20));r=self.assess(o)
        self.assertEqual(r["reason"],"BOUNDARY_UNCERTAIN");self.assertIsNone(r["recipe_id"])
        self.assertEqual(self.bank.patterns(),[])

    def test_color_conflict_does_not_prune_candidate_or_create(self):
        r=self.assess(observation("conflict",((3,3.1),(1,1.1)),(0,0,255)))
        self.assertEqual(r["reason"],"COLOR_CONFLICT");self.assertEqual(r["timing"]["possible_recipe_ids"],[7])
        self.assertEqual(self.bank.patterns(),[])

    def test_exact_retry_is_idempotent(self):
        o=observation("retry");a=self.bank.assess(o);b=self.bank.assess(o)
        self.assertEqual(a["assessment"],b["assessment"]);self.assertTrue(b["idempotent_replay"])
        self.assertEqual(self.bank.patterns()[0]["occurrence_count"],1)

    def test_changed_evidence_cannot_overwrite_identity(self):
        o=observation("same");self.assess(o);changed=deepcopy(o);changed["raw_rgb"]["nominal"]=[31,60,80]
        with self.assertRaises(ValueError):self.assess(changed)
        self.assertEqual(self.bank.patterns()[0]["occurrence_count"],1)

    def test_restart_retains_bank_and_reuse(self):
        self.assess(observation("first"));self.bank.close();self.bank=self.open()
        self.assertEqual(self.assess(observation("repeat"))["recipe_id"],100)

    def test_transaction_rolls_back_partial_creation(self):
        original=self.bank._save_assessment
        def fail(*args):raise RuntimeError("injected failure after tentative pattern insert")
        self.bank._save_assessment=fail
        with self.assertRaises(RuntimeError):self.assess(observation("rollback"))
        self.bank._save_assessment=original
        self.assertEqual(self.bank.patterns(),[])
        self.assertEqual(self.bank.connection.execute("SELECT COUNT(*) FROM demo_assessments").fetchone()[0],0)

    def test_concurrent_first_fills_create_one_pattern(self):
        def assess(i):
            bank=self.open()
            try:return bank.assess(observation(f"parallel-{i}"))["assessment"]["recipe_id"]
            finally:bank.close()
        with ThreadPoolExecutor(max_workers=4) as pool:ids=list(pool.map(assess,range(4)))
        self.assertEqual(set(ids),{100});self.assertEqual(self.bank.patterns()[0]["occurrence_count"],4)

    def test_midpoint_or_invented_duration_rejected(self):
        o=observation("bad duration");o["duration_bounds_seconds"][0]=[30.05,30.05]
        with self.assertRaises(ValueError):self.assess(o)

    def test_ambiguous_reference_ids_stay_unresolved(self):
        extra=deepcopy(REFERENCES[0]);extra["recipe_id"]=8;extra["vial_uid"]="synthetic-reference-8"
        self.bank.close();self.path=Path(self.folder.name)/"ambiguous.sqlite3";self.bank=self.open(REFERENCES+[extra])
        r=self.assess(observation("ambiguous",((3,3.1),(1,1.1)),(100,40,20)))
        self.assertEqual(r["reason"],"AMBIGUOUS");self.assertEqual(self.bank.patterns(),[])

    def test_normal_database_path_rejected(self):
        with self.assertRaises(ValueError):DemoBank(PROJECT_BANK,REFERENCES,RULES,NOMINAL,
            normal_paths=[PROJECT_BANK],bundle_revision="test",allow_development_writes=True)

    def test_development_writes_require_explicit_opt_in(self):
        with self.assertRaises(ValueError):DemoBank(self.path,REFERENCES,RULES,NOMINAL,
            normal_paths=[PROJECT_BANK],bundle_revision="test")

    def test_bad_sample_phase_does_not_create(self):
        o=observation("wrong phase");o["sample_actual_seconds"]=[.1,.2,.3]
        self.assertEqual(self.assess(o)["action"],"UNRESOLVED");self.assertEqual(self.bank.patterns(),[])

    def test_invalid_batch_rolls_back_all_tentative_changes(self):
        bad=observation("incomplete");bad["source_episode_intervals"][0]["end"]=None
        with self.assertRaises(ValueError):self.bank.assess_many([observation("good"),bad])
        self.assertEqual(self.bank.patterns(),[])
        self.assertEqual(self.bank.counts()["saved_assessments"],0)


PROJECT_BANK=HERE.parent/".data/recipes.sqlite3"
if __name__=="__main__":unittest.main()
