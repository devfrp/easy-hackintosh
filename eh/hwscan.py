"""eh.hwscan — scan matériel cross-platform → build/hardware.json."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from . import common as c


def _intel_uarch(model: str) -> str:
    m = model
    table = [
        (r"i[3579]-1[34]\d{2,3}", "raptor-lake"),
        (r"i[3579]-12\d{2,3}|N95|N100|N200|N305", "alder-lake"),
        (r"i[3579]-11\d{2,3}|11th Gen", "rocket-tiger-lake"),
        (r"i[3579]-10\d{2,3}|10th Gen", "comet-ice-lake"),
        (r"i[3579]-[89]\d{2,3}", "coffee-lake"),
        (r"i[3579]-7\d{2,3}", "kaby-lake"),
        (r"i[3579]-6\d{2,3}", "skylake"),
        (r"i[3579]-5\d{2,3}", "broadwell"),
        (r"i[3579]-4\d{2,3}", "haswell"),
    ]
    for rx, name in table:
        if re.search(rx, m):
            return name
    return "intel-unknown"


def _audio_layout(codec: str) -> int:
    c_ = codec
    if re.search(r"ALC25[567]", c_):
        return 17
    if re.search(r"ALC29[58]", c_):
        return 11
    if re.search(r"ALC(887|888|1220)", c_):
        return 7
    return 1


def _classify_eth(text: str) -> str:
    t = text.lower()
    if "intel" in t:
        return "IntelMausi"
    if "rtl8125" in t or "2.5g" in t:
        return "LucyRTL8125Ethernet"
    if "realtek" in t:
        return "RealtekRTL8111"
    return ""


def _classify_wifi(text: str) -> str:
    t = text.lower()
    if "broadcom" in t or "bcm" in t:
        return "AirportBrcmFixup"
    if "intel" in t:
        return "AirportItlwm (OpenIntelWireless, manuel)"
    if "atheros" in t:
        return "(Atheros: support limité)"
    return ""


# --------------------------------------------------------------------------- Linux
def _scan_linux() -> dict:
    d: dict = {}
    lscpu = subprocess.run(["lscpu"], capture_output=True, text=True,
                           env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"}).stdout
    vend = re.search(r"Vendor ID:\s*(.+)", lscpu)
    model = re.search(r"Model name:\s*(.+)", lscpu)
    d["cpu_vendor"] = vend.group(1).strip() if vend else ""
    d["cpu_model"] = model.group(1).strip() if model else ""
    if d["cpu_vendor"] == "GenuineIntel":
        d["cpu_family"], d["cpu_arch"] = "intel", _intel_uarch(d["cpu_model"])
    elif d["cpu_vendor"] == "AuthenticAMD":
        d["cpu_family"], d["cpu_arch"] = "amd", "amd-ryzen"
    else:
        d["cpu_family"], d["cpu_arch"] = "unknown", "unknown"

    ct = Path("/sys/class/dmi/id/chassis_type")
    d["chassis"] = "laptop" if (ct.is_file() and ct.read_text().strip()
                                in {"8", "9", "10", "11", "14"}) else "desktop"

    lspci = subprocess.run(["lspci", "-nn"], capture_output=True, text=True).stdout
    igpu = dgpu = ""
    for line in lspci.splitlines():
        if re.search(r"VGA|3D|Display", line):
            if "Intel" in line:
                igpu = line.strip()
            elif re.search(r"AMD/ATI|Advanced Micro", line):
                dgpu = "amd:" + line.strip()
            elif "NVIDIA" in line:
                dgpu = "nvidia:" + line.strip()
    d["igpu"], d["dgpu"] = igpu, dgpu

    eth = "\n".join(l for l in lspci.splitlines() if "Ethernet" in l)
    d["eth"], d["eth_kext"] = eth, _classify_eth(eth)
    wifi = "\n".join(l for l in lspci.splitlines()
                     if re.search(r"Network controller|Wireless", l))
    d["wifi"], d["wifi_kext"] = wifi, _classify_wifi(wifi)

    codec = ""
    for p in Path("/proc/asound").glob("card*/codec#*"):
        try:
            m = re.search(r"Codec:\s*(.+)", p.read_text())
            if m:
                codec = m.group(1).strip()
                break
        except OSError:
            pass
    d["audio_codec"], d["audio_layout"] = codec, _audio_layout(codec)
    d["nvme"] = Path("/dev/nvme0n1").exists()
    return d


# --------------------------------------------------------------------------- Windows
_PS = r"""
$o = [ordered]@{}
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$o.cpu_model = $cpu.Name; $o.cpu_vendor = $cpu.Manufacturer
$o.chassis = (Get-CimInstance Win32_SystemEnclosure).ChassisTypes -join ','
$o.gpus = (Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name }) -join '|'
$o.net = (Get-CimInstance Win32_NetworkAdapter | Where-Object { $_.PhysicalAdapter } |
          ForEach-Object { $_.Name + ' [' + $_.PNPDeviceID + ']' }) -join '|'
$o.audio = (Get-CimInstance Win32_SoundDevice | ForEach-Object { $_.Name }) -join '|'
try { $o.nvme = [bool](Get-PhysicalDisk | Where-Object BusType -eq 'NVMe') } catch { $o.nvme = $false }
$o | ConvertTo-Json -Compress
"""


def _scan_windows() -> dict:
    raw = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS],
        capture_output=True, text=True).stdout
    w = json.loads(raw)
    d: dict = {}
    d["cpu_model"] = (w.get("cpu_model") or "").strip()
    vend = (w.get("cpu_vendor") or "")
    d["cpu_vendor"] = "GenuineIntel" if "Intel" in vend else (
        "AuthenticAMD" if ("AMD" in vend or "Advanced Micro" in vend) else vend)
    if d["cpu_vendor"] == "GenuineIntel":
        d["cpu_family"], d["cpu_arch"] = "intel", _intel_uarch(d["cpu_model"])
    elif d["cpu_vendor"] == "AuthenticAMD":
        d["cpu_family"], d["cpu_arch"] = "amd", "amd-ryzen"
    else:
        d["cpu_family"], d["cpu_arch"] = "unknown", "unknown"

    # ChassisTypes 8/9/10/11/14 = portable
    ch = {x.strip() for x in (w.get("chassis") or "").split(",")}
    d["chassis"] = "laptop" if ch & {"8", "9", "10", "11", "14"} else "desktop"

    igpu = dgpu = ""
    for g in filter(None, (w.get("gpus") or "").split("|")):
        if "Intel" in g:
            igpu = g
        elif re.search(r"AMD|Radeon", g):
            dgpu = "amd:" + g
        elif "NVIDIA" in g:
            dgpu = "nvidia:" + g
    d["igpu"], d["dgpu"] = igpu, dgpu

    nets = list(filter(None, (w.get("net") or "").split("|")))
    wifi = "\n".join(n for n in nets
                     if re.search(r"Wi-?Fi|Wireless|WLAN|802\.11", n, re.I))
    eth = "\n".join(n for n in nets if n not in wifi)
    d["eth"], d["eth_kext"] = eth, _classify_eth(eth)
    d["wifi"], d["wifi_kext"] = wifi, _classify_wifi(wifi)

    codec = ""
    for a in filter(None, (w.get("audio") or "").split("|")):
        m = re.search(r"ALC\d+", a)
        if m:
            codec = a
            break
    d["audio_codec"], d["audio_layout"] = codec, _audio_layout(codec)
    d["nvme"] = bool(w.get("nvme"))
    return d


def scan() -> dict:
    c.title("Scan du matériel")
    if c.IS_WINDOWS:
        d = _scan_windows()
    elif c.IS_LINUX:
        d = _scan_linux()
    else:
        c.die("OS non supporté pour le scan (Linux ou Windows)")
    c.HWENV.write_text(json.dumps(d, indent=2, ensure_ascii=False))

    c.ok(f"CPU : {d['cpu_model'] or '?'}  [{d['cpu_family']}/{d['cpu_arch']}]")
    c.ok(f"Châssis : {d['chassis']}")
    if d["igpu"]:
        c.ok(f"iGPU : {d['igpu']}")
    if d["dgpu"]:
        c.ok(f"dGPU : {d['dgpu']}")
    if d["eth"]:
        c.ok(f"Ethernet : {d['eth_kext'] or 'inconnu'}")
    if d["wifi"]:
        c.ok(f"Wi-Fi : {d['wifi_kext'] or 'inconnu'}")
    if d["audio_codec"]:
        c.ok(f"Audio : {d['audio_codec']} (layout-id {d['audio_layout']})")
    c.ok(f"Scan écrit → {c.HWENV}")
    return d


def load() -> dict:
    if not c.HWENV.exists():
        return scan()
    return json.loads(c.HWENV.read_text())
