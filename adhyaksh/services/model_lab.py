"""Service layer for the Model Lab page: the only adhyaksh functions that page may call.

Pages import nothing from adhyaksh except services and ui (tests/test_engineering.py checks this), so
the tools, models and storage behind a page can change without touching the page.
"""
from __future__ import annotations

from adhyaksh import config
from adhyaksh.nlu import dataset, evaluate, registry, train

# adhyaksh.config
get = config.get
set_value = config.set_value

# adhyaksh.nlu.dataset
INTENTS = dataset.INTENTS
LANGS = dataset.LANGS
dataset_add_example = dataset.add_example
dataset_dataset_hash = dataset.dataset_hash
dataset_load = dataset.load

# adhyaksh.nlu.evaluate
evaluate_latest_runs = evaluate.latest_runs

# adhyaksh.nlu.registry
registry_set_active = registry.set_active

# adhyaksh.nlu.train
train_start_background = train.start_background
train_status = train.status
