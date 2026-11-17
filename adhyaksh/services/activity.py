"""Service layer for the Activity page: the only adhyaksh functions that page may call.

Pages import nothing from adhyaksh except services and ui (tests/test_engineering.py checks this), so
the tools, models and storage behind a page can change without touching the page.
"""
from __future__ import annotations

from adhyaksh.safety import audit

# adhyaksh.safety.audit
audit_list_recent = audit.list_recent
