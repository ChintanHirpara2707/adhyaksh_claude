"""Service layer for the Memory page: the only adhyaksh functions that page may call.

Pages import nothing from adhyaksh except services and ui (tests/test_engineering.py checks this), so
the tools, models and storage behind a page can change without touching the page.
"""
from __future__ import annotations

from adhyaksh import config
from adhyaksh.memory import store


def auto_memory_enabled() -> bool:
    return config.get_bool("auto_memory")


def set_auto_memory(on: bool) -> None:
    config.set_value("auto_memory", bool(on))


# adhyaksh.memory.store
store_delete_fact = store.delete_fact
store_list_facts = store.list_facts
store_save_fact = store.save_fact
store_update_fact = store.update_fact
