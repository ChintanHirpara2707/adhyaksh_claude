"""Service layer for the Tools page: the only adhyaksh functions that page may call.

Pages import nothing from adhyaksh except services and ui (tests/test_engineering.py checks this), so
the tools, models and storage behind a page can change without touching the page.
"""
from __future__ import annotations

from adhyaksh import config
from adhyaksh.result import E_NEEDS_CONFIRM
from adhyaksh.safety import policy
from adhyaksh.tools import apps, files, processes, reminders, system

# adhyaksh.tools.apps
apps_allowlist = apps.allowlist
apps_close_app = apps.close_app
apps_open_app = apps.open_app

# adhyaksh.config
get = config.get

# adhyaksh.tools.files
files_list_dir = files.list_dir

# adhyaksh.safety.policy
policy_cancel_guarded = policy.cancel_guarded

# adhyaksh.tools.processes
processes_kill_process = processes.kill_process
processes_list_processes = processes.list_processes

# adhyaksh.tools.reminders
reminders_cancel = reminders.cancel
reminders_list_pending = reminders.list_pending

# adhyaksh.tools.system
system_status = system.status
