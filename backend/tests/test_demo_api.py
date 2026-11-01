from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app import create_app
from recipes.demo_api import ASSETS
from recipes.demo_store import validate_demo_location
from recipes.durable import SQLiteStore

PREFIX="/api/recipe-workflow/demo"
AUTH={"Authorization":"Bearer synthetic-demo-test-token"}


class DemoAPITests(unittest.TestCase):
    def setUp(self):
        env=patch.dict(os.environ,{"INFERENCE_TOKEN":"synthetic-demo-test-token","RECIPE_DEMO_ENABLED":"false"})
        env.start();self.addCleanup(env.stop)
        self.folder=TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name);self.normal=self.root/"normal.sqlite3";self.demo=self.root/"demo.sqlite3"
        self.apps=[];self.addCleanup(self.close_apps)
        self.app=self.make_app();self.client=self.app.test_client()

    def make_app(self,**overrides):
        config={"TESTING":True,"MODEL_MODE":"mock","TRACKER_SCHEDULER_ENABLED":False,
            "RECIPE_DB_PATH":str(self.normal),"RECIPE_DEMO_ENABLED":True,"RECIPE_DEMO_DB_PATH":str(self.demo)}
        config.update(overrides)
        app=create_app({},config);self.apps.append(app);return app

    def close_apps(self):
        for app in self.apps:
            app.extensions["tracker_manager"].shutdown()
            if app.extensions["recipe_demo_service"]:app.extensions["recipe_demo_service"].bank.close()
            if app.extensions["recipe_store"]:app.extensions["recipe_store"].close()

    def post(self,path,client=None,body=None):
        return (client or self.client).post(PREFIX+path,json={} if body is None else body,headers=AUTH)

    def get(self,path):return self.client.get(PREFIX+path,headers=AUTH)

    def run_all(self,client=None):
        first=self.post("/videos/video-1/assessments",client)
        second=self.post("/videos/video-2/assessments",client)
        self.assertEqual(first.status_code,200,first.get_json());self.assertEqual(second.status_code,200,second.get_json())
        return first.get_json()["results"]+second.get_json()["results"]

    def test_disabled_by_default_has_no_demo_store(self):
        path=self.root/"never-created.sqlite3"
        app=self.make_app(RECIPE_DEMO_ENABLED=False,RECIPE_DEMO_DB_PATH=str(path))
        client=app.test_client()
        r=client.get(PREFIX+"/status",headers=AUTH)
        self.assertFalse(r.get_json()["enabled"]);self.assertFalse(path.exists())
        self.assertEqual(self.post("/recorded/video-1/V1-V06",client).status_code,503)

    def test_status_and_gets_do_not_assess_or_learn(self):
        r=self.get("/status");self.assertEqual(r.status_code,200)
        d=r.get_json();self.assertFalse(d["automatic_video_detection"])
        self.assertEqual(d["video_counts"],{"video-1":19,"video-2":3})
        self.assertEqual(d["counts"]["saved_assessments"],0)
        self.assertEqual(self.get("/recorded/video-1/V1-V06").status_code,404)
        self.assertEqual(self.get("/recipes").get_json()["recipes"],[])
        self.assertEqual(r.headers["X-Recipe-Storage"],"isolated_demo_sqlite")

    def test_archival_inputs_preserve_original_quality_reasons_and_require_tracking(self):
        results=self.run_all()
        expected=json.loads((Path(__file__).parent/"fixtures/recipe_demo_expected.json").read_text())
        by_source={r["assessment"]["observation_id"]:r["assessment"] for r in results}
        # Keep the original offline oracle frozen. Version 1.4 adds a mandatory
        # tracking hold to archived inputs rather than rewriting their data.
        for legacy in expected:
            item={**legacy,'action':'UNRESOLVED','reason':'OBSERVATION_CHECK_FAILED','recipe_id':None,'recipe_status':None,
                  'hold_reasons':sorted(set(legacy['hold_reasons']+['TRACKING_EVIDENCE_MISSING']))}
            actual=by_source[item["observation_id"]]
            for k,v in item.items():
                self.assertEqual(actual["observation"].get(k) if k in ("video_id","vial_id") else actual[k],v,(item["observation_id"],k))
        patterns=self.get("/recipes").get_json()["recipes"]
        self.assertEqual(patterns,[])

    def test_archival_source_retrieval_cannot_create_or_reuse_patterns(self):
        a=self.post("/recorded/video-1/V1-V06").get_json()
        b=self.post("/recorded/video-1/V1-V12").get_json()
        self.assertEqual(a["assessment"]["action"],"UNRESOLVED")
        self.assertEqual(b["assessment"]["action"],"UNRESOLVED")
        self.assertEqual(a["assessment"]["recipe_id"],b["assessment"]["recipe_id"])
        stored=self.get("/recorded/video-1/V1-V06").get_json()["assessment"]
        self.assertEqual(stored,a["assessment"])
        self.assertEqual(self.get("/recipes/100").status_code,404)
        self.assertEqual(len(self.get("/videos/video-1/assessments").get_json()["assessments"]),2)

    def test_all_retries_do_not_duplicate_patterns_or_occurrences(self):
        first=self.run_all();before=self.get("/status").get_json()["counts"]
        second=self.run_all();after=self.get("/status").get_json()["counts"]
        self.assertEqual(before,after);self.assertTrue(all(x["idempotent_replay"] for x in second))
        self.assertEqual([x["assessment"] for x in first],[x["assessment"] for x in second])
        self.assertEqual(self.post("/videos/video-1/assessments").get_json()["new_patterns"],0)

    def test_boundaries_and_color_holds_remain_unresolved(self):
        for vial,reason in (("V1-V02","BOUNDARY_UNCERTAIN"),("V1-V13","COLOR_CONFLICT"),("V1-V07","OBSERVATION_CHECK_FAILED")):
            r=self.post("/recorded/video-1/"+vial).get_json()["assessment"]
            self.assertEqual(r["action"],"UNRESOLVED");self.assertIsNone(r["recipe_id"])
            self.assertIn("TRACKING_EVIDENCE_MISSING",r["hold_reasons"])
            if reason=="BOUNDARY_UNCERTAIN":self.assertEqual(r["timing"]["status"],reason)
            if reason=="COLOR_CONFLICT":self.assertEqual(r["color"]["status"],"CONFLICTING")
        self.assertEqual(self.get("/recipes").get_json()["recipes"],[])

    def test_client_cannot_supply_measurements_ids_or_creation_policy(self):
        for body in ({"raw_rgb":[1,2,3]},{"recipe_id":100},{"allow_creation":True},[],"{}"):
            self.assertEqual(self.post("/recorded/video-1/V1-V06",body=body).status_code,400)
        self.assertEqual(self.get("/status").get_json()["counts"]["saved_assessments"],0)

    def test_unknown_sources_do_not_write(self):
        for path in ("/recorded/video-4/V4-V01","/recorded/video-1/missing","/videos/not-a-video/assessments"):
            self.assertEqual(self.post(path).status_code,404)
        self.assertEqual(self.get("/recipes/999").status_code,404)

    def test_token_and_origin_checks_apply(self):
        self.assertEqual(self.client.post(PREFIX+"/recorded/video-1/V1-V06",json={}).status_code,401)
        self.assertEqual(self.client.get(PREFIX+"/status").status_code,401)
        self.assertEqual(self.client.post(PREFIX+"/recorded/video-1/V1-V06",json={},headers={**AUTH,"Origin":"https://foreign.invalid"}).status_code,403)
        with patch.dict(os.environ,{"INFERENCE_TOKEN":""}):
            self.assertEqual(self.client.post(PREFIX+"/recorded/video-1/V1-V06",json={}).status_code,503)

    def test_normal_bank_unchanged_by_all_demo_writes(self):
        store=self.app.extensions["recipe_store"]
        before=[tuple(row) for row in store.connection.execute("SELECT * FROM recipe_state")]
        trial_before=store.connection.execute("SELECT COUNT(*) FROM recipe_trial_assessments").fetchone()[0]
        self.run_all()
        self.assertEqual(before,[tuple(row) for row in store.connection.execute("SELECT * FROM recipe_state")])
        self.assertEqual(trial_before,store.connection.execute("SELECT COUNT(*) FROM recipe_trial_assessments").fetchone()[0])
        tables={r[0] for r in store.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn("demo_patterns",tables)

    def test_restart_preserves_held_archival_assessments(self):
        self.post("/recorded/video-1/V1-V06")
        original=self.get("/recorded/video-1/V1-V06").get_json()["assessment"]
        client=self.make_app().test_client()
        replay=self.post("/recorded/video-1/V1-V06",client).get_json()
        self.assertTrue(replay["idempotent_replay"])
        self.post("/recorded/video-1/V1-V12",client)
        self.assertEqual(replay["assessment"],original)
        self.assertEqual(self.get("/recipes").get_json()["recipes"],[])

    def test_concurrent_api_retries_create_one_entry(self):
        def submit(_):
            with self.app.test_client() as client:return self.post("/recorded/video-1/V1-V06",client).get_json()
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(submit,range(4)))
        self.assertEqual(sum(not r["idempotent_replay"] for r in results),1)
        self.assertEqual(self.get("/status").get_json()["counts"],{"discovered_patterns":0,"saved_assessments":1,"linked_occurrences":0})

    def test_batch_runtime_failure_rolls_back_the_entire_request(self):
        bank=self.app.extensions["recipe_demo_service"].bank;original=bank._save_assessment
        def fail_late(key,*args):
            if key.endswith("visit-012"):raise RuntimeError("synthetic batch failure after tentative discovery")
            return original(key,*args)
        with patch.object(bank,"_save_assessment",side_effect=fail_late),self.assertLogs(self.app.logger,level="ERROR"):
            r=self.post("/videos/video-1/assessments")
        self.assertEqual(r.status_code,500)
        self.assertEqual(self.get("/status").get_json()["counts"],{"discovered_patterns":0,"saved_assessments":0,"linked_occurrences":0})
        self.assertEqual(self.post("/videos/video-1/assessments").status_code,200)

    def test_configuration_rejects_normal_path_symlink_and_hardlink(self):
        for path in (self.normal,self.root/"symlink.sqlite3",self.root/"hardlink.sqlite3"):
            if path.name=="symlink.sqlite3":path.symlink_to(self.normal)
            if path.name=="hardlink.sqlite3":os.link(self.normal,path)
            with self.assertRaises(ValueError):self.make_app(RECIPE_DEMO_DB_PATH=str(path))

    def test_enabled_requires_explicit_separate_path_and_boolean(self):
        for config in ({"RECIPE_DEMO_DB_PATH":""},{"RECIPE_DEMO_DB_PATH":":memory:"},{"RECIPE_DEMO_ENABLED":"false"}):
            with self.assertRaises(ValueError):self.make_app(**config)

    def test_normal_bank_copy_is_rejected_by_its_schema(self):
        target=self.root/"normal-copy.sqlite3"
        self.app.extensions["recipe_store"].connection.execute("PRAGMA wal_checkpoint(FULL)")
        shutil.copy2(self.normal,target)
        with self.assertRaisesRegex(ValueError,"normal recipe-bank tables"):
            self.make_app(RECIPE_DEMO_DB_PATH=str(target))

    def test_tampered_assets_fail_before_opening_demo_bank(self):
        target=self.root/"assets";shutil.copytree(ASSETS,target)
        (target/"recorded_observations.json").write_text("{}")
        fresh=self.root/"tampered-demo.sqlite3"
        with self.assertRaisesRegex(ValueError,"integrity"):
            self.make_app(RECIPE_DEMO_ASSETS=target,RECIPE_DEMO_DB_PATH=str(fresh))
        self.assertFalse(fresh.exists())

    def test_failed_demo_initialization_closes_normal_store_connection(self):
        stores=[]
        def remember(path):
            store=SQLiteStore(path);stores.append(store);return store
        with patch("app.SQLiteStore",side_effect=remember),patch("app.RecordedDemoService",side_effect=ValueError("synthetic invalid assets")):
            with self.assertRaises(ValueError):self.make_app()
        with self.assertRaises(sqlite3.ProgrammingError):stores[0].connection.execute("SELECT 1")

    def test_portable_assets_and_responses_have_no_research_paths(self):
        payload=(ASSETS/"recorded_observations.json").read_text()
        self.assertNotIn("/Users/",payload);self.assertNotIn('"path":',payload)
        result=self.post("/recorded/video-1/V1-V06").get_data(as_text=True)
        self.assertNotIn("/Users/",result)
        self.assertIn('"evidence_id"',result)

    def test_reference_color_exclusions_are_exposed_without_removing_timing_profiles(self):
        result=self.post("/recorded/video-1/V1-V01").get_json()["assessment"]
        quality=result["color"]["reference_color_qualification"]
        self.assertEqual(quality["qualified_profile_count"],40)
        self.assertEqual({x["profile_id"] for x in quality["excluded_profiles"]},
            {"v5_e03","field_v04","field_v09","field_v18"})
        self.assertEqual(result["timing"]["possible_recipe_ids"],[7])
        self.assertEqual(result["action"],"UNRESOLVED")
        self.assertEqual(len(self.app.extensions["recipe_demo_service"].bank.references),44)

    def test_pending_confirmed_history_is_visible_across_videos_and_restart(self):
        data=json.loads((Path(__file__).parent/"fixtures/two_fill_observations.json").read_text())["observations"]
        bank=self.app.extensions["recipe_demo_service"].bank
        from backend.tests.recorded_tracking_fixtures import with_tracking
        data=[with_tracking(o) for o in data]
        bank.assess_many([o for o in data if o["video_id"]=="video-1"])
        groups=self.get("/patterns").get_json()["groups"]
        self.assertEqual(sum(g["status"]=="PENDING_REPEAT" for g in groups),3)
        first=self.get("/producer/videos/video-1").get_json()
        before=next(a for a in first["assessments"] if a["observation"]["vial_id"]=="V1-V13")
        self.assertEqual(before["pattern_membership"]["status"],"PENDING_REPEAT")
        bank.assess_many([o for o in data if o["video_id"]=="video-2"])
        second=self.get("/producer/videos/video-1").get_json()
        after=next(a for a in second["assessments"] if a["observation"]["vial_id"]=="V1-V13")
        self.assertEqual(after["pattern_membership"]["recipe_id"],102)
        self.assertEqual(after["color"]["status"],"CONFLICTING");self.assertIsNone(after["recipe_id"])
        group=after["pattern_membership"]["group_id"]
        history=self.get(f"/patterns/{group}/history").get_json()
        self.assertEqual(len(history["members"]),2)
        self.assertTrue(all(len(m["history"])==2 for m in history["members"]))
        restarted=self.make_app().test_client()
        saved=restarted.get(PREFIX+"/patterns",headers=AUTH).get_json()["groups"]
        self.assertEqual(sum(g["status"]=="PENDING_REPEAT" for g in saved),2)
        self.assertEqual(self.get("/patterns/unknown/history").status_code,404)

if __name__=="__main__":unittest.main()


