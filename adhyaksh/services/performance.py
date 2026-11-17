"""Service layer for the PC Performance page: the only adhyaksh functions that page may call.

Pages import nothing from adhyaksh except services and ui (tests/test_engineering.py checks this), so
the tools, models and storage behind a page can change without touching the page.
"""
from __future__ import annotations

from adhyaksh import config
from adhyaksh.tools import boost

# adhyaksh.tools.boost
boost_clean_temp = boost.clean_temp
boost_scan_temp = boost.scan_temp
boost_stats = boost.stats

# adhyaksh.config
get = config.get
