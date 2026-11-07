# Assumptions

- 2026-11-06: D-02, D-04 and D-06 were left as placeholders; defaults applied (Windows 11, Python 3.11, no key, 3 GB free).
- 2026-11-06: Streamlit 1.46 or newer is required for st.navigation(position="hidden"). Exact version is pinned after first install.
- 2026-11-06: The user profile root folder itself is treated as a system path (L3); folders inside it, such as Documents, are allowed when listed as allowed roots.
- 2026-11-06: Dark-mode switch is a labelled toggle ("Dark mode") instead of sun and moon icons, for reliable keyboard and screen-reader labels in Streamlit.
