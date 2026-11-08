"""Reproduction script: web commands typed + voice variants."""
import os, json
from pathlib import Path
from adhyaksh import config
from adhyaksh.chat import context, engine, router
from adhyaksh.nlu import train
from tests.helpers import fresh_env

base = fresh_env()
db_init = __import__("adhyaksh.db", fromlist=["init"]); db_init.init()
ws = base / "ws"; ws.mkdir()
config.set_value("allowed_folders", json.dumps([str(ws)]))
config.set_value("default_work_folder", str(ws))
train.train_all(42, kinds=["m1_logreg", "m3_svm"], write_report=False)
cid = context.new_conversation()

CASES = [
    "search Chintan hirpara in a new tab",
    "search for python tutorials",
    "open github in a new tab",
    "open a new tab",
    "open youtube",
    "go to gmail dot com",
    "open linkedin dot com",
]

for c in CASES:
    variants = [c, c.lower(), c.lower().rstrip(".!?"), c.lower().rstrip(".!?") + "."]
    for v in variants:
        r = router.match_rules(v)
        url = router._web_url(v) if r and r.intent == "web_open" else None
        print(f"{v!r:55s} -> intent={r.intent if r else None!r:12s} url={url!r}")
    print()
