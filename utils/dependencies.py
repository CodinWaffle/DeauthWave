"""Startup environment check: Linux-only, and makes sure the required
command-line tools (the aircrack-ng suite) are installed before the
DeauthWave menu loads."""

import os
import platform
import shutil
import subprocess
import time

from utils import banner

# tool name -> apt package that provides it (Debian-based distros: Kali, Parrot, Ubuntu, ...)
REQUIRED_TOOLS = {
    "airmon-ng": "aircrack-ng",
    "airodump-ng": "aircrack-ng",
    "aireplay-ng": "aircrack-ng",
}

CHECK_SPIN_SECONDS = 0.45  # purely cosmetic pause so each row reads as "checking..." instead of popping in instantly


def detect_distro():
    try:
        with open("/etc/os-release") as f:
            data = {}
            for line in f:
                if "=" in line:
                    key, _, value = line.strip().partition("=")
                    data[key] = value.strip('"')
        return data.get("PRETTY_NAME", "unknown Linux distro")
    except FileNotFoundError:
        return "unknown Linux distro"


def _render_checklist(rows, prev_lines, spin_tick=0):
    """rows: list of (label, detail, status) with status 'pending' / 'ok' / 'fail'.
    Rewinds only the box's own line count instead of re-clearing the whole
    screen and reprinting the big logo/links block on every tick."""
    banner.rewind(prev_lines)

    lines = []
    for label, detail, status in rows:
        if status == "pending":
            spin = banner.spinner_frame(spin_tick, accent=banner.C.CYAN)
            lines.append(f"{spin}  {label}...")
        elif status == "ok":
            icon = f"{banner.C.OK}{banner.C.BOLD}✓{banner.C.RESET}"
            lines.append(f"{icon}  {label:<16}{banner.C.MUTED}{detail}{banner.C.RESET}")
        else:
            icon = f"{banner.C.DANGER}{banner.C.BOLD}✗{banner.C.RESET}"
            lines.append(f"{icon}  {label:<16}{banner.C.DANGER}{detail}{banner.C.RESET}")

    return banner.box(lines, title="system check", accent=banner.C.CYAN)


def _run_check(rows, index, check_fn, prev_lines):
    """Animate a spinner on rows[index] while "checking", then lock in the result.
    check_fn takes no args and returns (ok, detail). Returns (ok, prev_lines)."""
    ticks = max(1, int(CHECK_SPIN_SECONDS / 0.08))
    for tick in range(ticks):
        prev_lines = _render_checklist(rows, prev_lines, spin_tick=tick)
        time.sleep(0.08)

    ok, detail = check_fn()
    label = rows[index][0]
    rows[index] = (label, detail, "ok" if ok else "fail")
    prev_lines = _render_checklist(rows, prev_lines)
    return ok, prev_lines


def _check_platform():
    if platform.system() != "Linux":
        return False, f"unsupported OS: {platform.system()}"
    return True, detect_distro()


def _check_root():
    # os.geteuid() is POSIX-only — safe to call here since the platform check
    # above already confirmed we're on Linux before this runs
    if os.geteuid() != 0:
        return False, "not running as root"
    return True, "running as root"


def _check_tool(tool):
    path = shutil.which(tool)
    return path is not None, (path or f"not found (needs {REQUIRED_TOOLS[tool]})")


def install_packages(packages):
    if shutil.which("apt-get") is None:
        banner.error("apt-get not found — automatic install only supports Debian-based distros.")
        banner.info("install manually with your distro's package manager: " + ", ".join(packages))
        return False

    banner.info("installing: " + ", ".join(packages))
    subprocess.run(["sudo", "apt-get", "update"], check=False)
    result = subprocess.run(["sudo", "apt-get", "install", "-y", *packages])
    return result.returncode == 0


def ensure_dependencies():
    rows = [
        ("platform", "", "pending"),
        ("privileges", "", "pending"),
        *[(tool, "", "pending") for tool in REQUIRED_TOOLS],
    ]

    banner.banner()
    banner.section("environment check", accent=banner.C.CYAN)
    prev_lines = 0

    ok, prev_lines = _run_check(rows, 0, _check_platform, prev_lines)
    if not ok:
        banner.error("DeauthWave only runs on Linux.")
        banner.info("monitor-mode wifi and packet injection aren't available on this OS.")
        banner.info("run this on Kali Linux or Parrot OS (or another Debian-based Linux).")
        raise SystemExit(1)

    distro = rows[0][1]
    if "kali" not in distro.lower() and "parrot" not in distro.lower():
        banner.warn("DeauthWave is built & tested on Kali Linux and Parrot OS.")
        banner.warn(f"'{distro}' may still work if it's Debian-based, but isn't officially tested.")

    ok, prev_lines = _run_check(rows, 1, _check_root, prev_lines)
    if not ok:
        banner.error("DeauthWave must be run as root.")
        banner.info("it drives airmon-ng, airodump-ng, and aireplay-ng directly,")
        banner.info("all of which need raw device access.")
        banner.info("run it again with: sudo python3 main.py")
        raise SystemExit(1)

    for i, tool in enumerate(REQUIRED_TOOLS, start=2):
        _, prev_lines = _run_check(rows, i, lambda t=tool: _check_tool(t), prev_lines)

    missing = [tool for tool, _, status in rows[2:] if status == "fail"]
    if not missing:
        banner.ok("all systems go.")
        return

    packages = sorted({REQUIRED_TOOLS[tool] for tool in missing})
    banner.warn("missing tools: " + ", ".join(missing))
    banner.info("provided by package(s): " + ", ".join(packages))

    choice = banner.prompt("install missing dependencies now? [Y/n]")
    if choice.strip().lower() not in ("", "y", "yes"):
        banner.error("DeauthWave needs these tools to run. install them and try again.")
        raise SystemExit(1)

    if not install_packages(packages):
        banner.error("automatic install failed — install manually: sudo apt install " + " ".join(packages))
        raise SystemExit(1)

    for i, tool in enumerate(REQUIRED_TOOLS, start=2):
        if rows[i][2] == "fail":
            _, prev_lines = _run_check(rows, i, lambda t=tool: _check_tool(t), prev_lines)

    still_missing = [tool for tool, _, status in rows[2:] if status == "fail"]
    if still_missing:
        banner.error("still missing after install: " + ", ".join(still_missing))
        raise SystemExit(1)

    banner.ok("dependencies installed")
