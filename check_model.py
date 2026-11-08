import json, os
from pathlib import Path
from adhyaksh import config, db
from adhyaksh.nlu import train, registry
from tests.helpers import fresh_env

base = fresh_env()
db.init()
ws = base / "ws"; ws.mkdir()
config.set_value("allowed_folders", json.dumps([str(ws)]))
config.set_value("default_work_folder", str(ws))
train.train_all(42, kinds=["m1_logreg"], write_report=False)
for t in ["shut down my laptop", "send an email", "create notes.txt", "open chrome"]:
    print(repr(t), "->", registry.predict(t))
