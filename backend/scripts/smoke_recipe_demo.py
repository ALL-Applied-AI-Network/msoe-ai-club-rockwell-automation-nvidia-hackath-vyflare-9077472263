"""Exercise the packaged demo through a temporary loopback HTTP server.

Uses empty inference registry and temporary normal/demo databases. It does not
touch a running server, load model weights, or change the real recipe bank.
"""
from collections import Counter
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.request import Request,urlopen
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from werkzeug.serving import make_server,WSGIRequestHandler
from app import create_app


class QuietHandler(WSGIRequestHandler):
    def log_request(self,*args,**kwargs):pass


def main():
    with TemporaryDirectory() as directory,patch.dict(os.environ,{"INFERENCE_TOKEN":"loopback-smoke-test-only","RECIPE_DEMO_ENABLED":"false"}):
        root=Path(directory)
        app=create_app({}, {"TESTING":True,"MODEL_MODE":"mock","TRACKER_SCHEDULER_ENABLED":False,
            "RECIPE_DB_PATH":str(root/"temporary-normal.sqlite3"),"RECIPE_DEMO_ENABLED":True,
            "RECIPE_DEMO_DB_PATH":str(root/"temporary-demo.sqlite3")})
        server=None;thread=None
        try:
            store=app.extensions["recipe_store"]
            normal_before=store.connection.execute("SELECT payload FROM recipe_state").fetchone()[0]
            server=make_server("127.0.0.1",0,app,request_handler=QuietHandler)
            thread=Thread(target=server.serve_forever);thread.start()
            url=f"http://127.0.0.1:{server.server_port}/api/recipe-workflow/demo"
            def call(path,method="GET"):
                req=Request(url+path,data=b"{}" if method=="POST" else None,method=method,
                    headers={"Authorization":"Bearer loopback-smoke-test-only","Content-Type":"application/json"})
                with urlopen(req,timeout=5) as response:
                    assert response.status==200
                    assert response.headers["X-Recipe-Storage"]=="isolated_demo_sqlite"
                    return json.loads(response.read())
            initial=call("/status");assert initial["counts"]["saved_assessments"]==0
            first=call("/videos/video-1/assessments","POST")
            second=call("/videos/video-2/assessments","POST")
            results=first["results"]+second["results"]
            counts=dict(Counter(r["assessment"]["action"] for r in results))
            assert counts=={"UNRESOLVED":18,"CREATE_DISCOVERED_PATTERN":2,"REUSE_DISCOVERED_PATTERN":1,"REUSE_REFERENCE_PATTERN":1}
            patterns=call("/recipes")["recipes"]
            assert [(p["recipe_id"],p["occurrence_count"]) for p in patterns]==[(100,2),(101,1)]
            again=[call(f"/videos/video-{v}/assessments","POST") for v in (1,2)]
            assert sum(r["replayed_assessments"] for r in again)==22
            assert all(r["new_patterns"]==r["new_assessments"]==0 for r in again)
            final=call("/status")
            assert final["counts"]=={"discovered_patterns":2,"saved_assessments":22,"linked_occurrences":4}
            assert store.connection.execute("SELECT payload FROM recipe_state").fetchone()[0]==normal_before
            assert store.connection.execute("SELECT COUNT(*) FROM recipe_trial_assessments").fetchone()[0]==0
            print(json.dumps({"real_loopback_http":True,"temporary_databases_only":True,"model_weights_loaded":False,
                "input_mode":initial["input_mode"],"action_counts":counts,"counts":final["counts"],
                "recipe_occurrences":[{"recipe_id":p["recipe_id"],"count":p["occurrence_count"]} for p in patterns],
                "replayed_assessments":22,"replay_added_patterns":0,"temporary_normal_store_unchanged":True,
                "real_application_database_opened":False,"frontend_changes":False,"server_stopped_after_test":True},indent=2))
        finally:
            if server:server.shutdown();server.server_close()
            if thread:thread.join(timeout=5)
            app.extensions["tracker_manager"].shutdown()
            app.extensions["recipe_demo_service"].bank.close()
            store.close()


if __name__=="__main__":main()
