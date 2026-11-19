"""Wi-Fi and Bluetooth: read their state, and switch them on or off.

Switching uses the Windows Runtime radios API (the same switch as the quick settings panel), which needs no
administrator rights, run through PowerShell with a fixed script: the radio kind and the state come from fixed
tables, never from user text. Turning a radio OFF is level 2 (it can cut the network the assistant itself uses), so
the user confirms; turning it ON is level 1. When Windows refuses (a policy, a missing radio, a laptop switch),
the result says so plainly: nothing is pretended.
"""
from __future__ import annotations

import os
import re

from adhyaksh.result import E_ACTION_FAILED, E_BAD_ARGUMENTS, E_UNSUPPORTED_OS, Result
from adhyaksh.safety import policy
from adhyaksh.tools.display import powershell

RADIOS = {"wifi": "WiFi", "bluetooth": "Bluetooth"}
_STATES = {True: "On", False: "Off"}
_AWAIT = (
    "$ErrorActionPreference = 'Stop'; Add-Type -AssemblyName System.Runtime.WindowsRuntime; "
    "$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and "
    "$_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]; "
    "function Await($op, $type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }; "
    "[Windows.Devices.Radios.Radio,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null; "
)
_LIST = _AWAIT + ("$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) "
                  "([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]]); "
                  "$radios | ForEach-Object { \"$($_.Kind)|$($_.State)\" }")
_SET = _AWAIT + ("$access = Await ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) ([Windows.Devices.Radios.RadioAccessStatus]); "
                 "if ($access -ne 'Allowed') { \"denied|$access\"; exit 0 }; "
                 "$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) "
                 "([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]]); "
                 "$r = $radios | Where-Object { $_.Kind -eq '{kind}' } | Select-Object -First 1; "
                 "if (-not $r) { 'missing|none'; exit 0 }; "
                 "$res = Await ($r.SetStateAsync('{state}')) ([Windows.Devices.Radios.RadioAccessStatus]); \"result|$res\"")


def _ctx(ctx: dict | None) -> dict:
    ctx = ctx or {}
    return {"user_text": ctx.get("user_text", ""), "intent": ctx.get("intent", "")}


def radios() -> Result:
    """{"wifi": True/False, "bluetooth": True/False} for the radios this PC has. Read-only."""
    if os.name != "nt":
        return Result.failure(E_UNSUPPORTED_OS, "Radio control works on Windows only.")
    ok, out = powershell(_LIST, timeout=20.0)
    if not ok:
        return Result.failure(E_ACTION_FAILED, "Windows did not report the state of Wi-Fi and Bluetooth.")
    state = {}
    for line in out.splitlines():
        kind, _, value = line.strip().partition("|")
        for key, win in RADIOS.items():
            if kind.casefold() == win.casefold():
                state[key] = value.strip().casefold() == "on"
    return Result.success(state)


def wifi_details() -> dict:
    """SSID and signal of the connected Wi-Fi network (netsh, read-only), or {} when not connected."""
    if os.name != "nt":
        return {}
    import subprocess
    try:
        out = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True, timeout=10,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {}
    info = {}
    for key, pat in (("state", r"^\s*State\s*:\s*(.+)$"), ("ssid", r"^\s*SSID\s*:\s*(.+)$"), ("signal", r"^\s*Signal\s*:\s*(\d+)%")):
        m = re.search(pat, out, re.MULTILINE | re.IGNORECASE)
        if m:
            info[key] = m.group(1).strip()
    return info


def status() -> Result:
    res = radios()
    if not res.ok:
        return res
    return Result.success({**res.data, "wifi_network": wifi_details()})


def set_radio(radio: str, on: bool, *, ctx: dict | None = None) -> Result:
    if radio not in RADIOS or not isinstance(on, bool):
        return Result.failure(E_BAD_ARGUMENTS, f"radio must be one of: {', '.join(RADIOS)}; on must be true or false.")
    if os.name != "nt":
        return Result.failure(E_UNSUPPORTED_OS, "Radio control works on Windows only.")
    action = "radio_on" if on else "radio_off"
    target = f"{'Wi-Fi' if radio == 'wifi' else 'Bluetooth'} {'on' if on else 'off'}"

    def go() -> Result:
        # Only two fixed tokens are substituted, from fixed tables (never user text).
        ok, out = powershell(_SET.replace("{kind}", RADIOS[radio]).replace("{state}", _STATES[on]), timeout=30.0)
        kind, _, detail = out.strip().splitlines()[-1].partition("|") if out.strip() else ("", "", "")
        if not ok or kind == "denied":
            return Result.failure(E_ACTION_FAILED, f"Windows did not allow switching {target} ({detail or 'no access'}). "
                                                   "Use the quick settings panel instead.")
        if kind == "missing":
            return Result.failure(E_ACTION_FAILED, f"This PC has no {radio} radio that Windows can switch.")
        if detail.strip().casefold() != "allowed":
            return Result.failure(E_ACTION_FAILED, f"Windows refused to switch {target} ({detail}).")
        return Result.success({"radio": radio, "on": on})

    return policy.run_guarded(action, target, go, token=(ctx or {}).get("token"), **_ctx(ctx))
