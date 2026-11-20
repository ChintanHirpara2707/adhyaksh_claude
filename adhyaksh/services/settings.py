"""Service layer for the Settings page: the only adhyaksh functions that page may call.

Pages import nothing from adhyaksh except services and ui (tests/test_engineering.py checks this), so
the tools, models and storage behind a page can change without touching the page.
"""
from __future__ import annotations

from adhyaksh import __version__, autostart, client, config, db
from adhyaksh.llm import base as llm
from adhyaksh.nlu import evaluate, registry
from adhyaksh.rag import embedder, retriever
from adhyaksh.tools import apps
from adhyaksh.voice import stt

# adhyaksh.client and adhyaksh.autostart (background engine)
client_available = client.available
client_forget_cache = client.forget_cache
autostart_enabled = autostart.enabled
autostart_enable = autostart.enable
autostart_disable = autostart.disable

# adhyaksh.tools.apps
apps_allowlist = apps.allowlist
apps_set_allowlist = apps.set_allowlist

# adhyaksh.config
configure_folders = config.configure_folders
data_dir = config.data_dir
get = config.get
get_allowed_roots = config.get_allowed_roots
get_bool = config.get_bool
get_float = config.get_float
set_value = config.set_value
SettingError = config.SettingError

# adhyaksh.db
db_export_bytes = db.export_bytes
db_schema_version = db.schema_version
db_wipe = db.wipe

# adhyaksh.rag.embedder
embedder_download = embedder.download
embedder_installed = embedder.installed
embedder_model_present = embedder.model_present

# adhyaksh.nlu.evaluate
evaluate_latest_runs = evaluate.latest_runs

# adhyaksh.llm.base
PROVIDERS = llm.PROVIDERS
llm_api_key = llm.api_key
llm_mask = llm.mask
llm_set_key = llm.set_key

# adhyaksh.nlu.registry
registry_reload = registry.reload
registry_set_active = registry.set_active

# adhyaksh.rag.retriever
retriever_embedding_mode = retriever.embedding_mode

# adhyaksh.voice.stt
SIZES = stt.SIZES
stt_download = stt.download
stt_installed = stt.installed
stt_model_present = stt.model_present
stt_model_size = stt.model_size

version = __version__
