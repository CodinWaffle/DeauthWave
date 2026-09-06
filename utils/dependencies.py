"""Startup environment check: Linux-only, and makes sure the required
command-line tools (the aircrack-ng suite) are installed before the
DeauthWave menu loads."""

import os
import platform
import shutil
import subprocess

from utils import banner

# tool name -> apt package that provides it (Debian-based distros: Kali, Parrot, Ubuntu, ...)
REQUIRED_TOOLS = {
    "airmon-ng": "aircrack-ng",
    "airodump-ng": "aircrack-ng",
    "aireplay-ng": "aircrack-ng",
}


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


def check_platform():
    if platform.system() != "Linux":
        banner.error(f"DeauthWave only runs on Linux — detected: {platform.system()}.")
        banner.error("monitor-mode wifi and packet injection aren't available on this OS.")
        banner.info("run this on Kali Linux or Parrot OS (or another Debian-based Linux).")
        raise SystemExit(1)

    distro = detect_distro()
    banner.ok(f"platform ok: linux — {distro}")
    if "kali" not in distro.lower() and "parrot" not in distro.lower():
        banner.warn("DeauthWave is built & tested on Kali Linux and Parrot OS.")
        banner.warn(f"'{distro}' may still work if it's Debian-based, but isn't officially tested.")


def check_root():
    # os.geteuid() is POSIX-only — safe to call here since check_platform()
    # already confirmed we're on Linux before this runs
    if os.geteuid() != 0:
        banner.error("DeauthWave must be run as root.")
        banner.info("it drives airmon-ng, airodump-ng, and aireplay-ng directly,")
        banner.info("all of which need raw device access.")
        banner.info("run it again with: sudo python3 main.py")
        raise SystemExit(1)
    banner.ok("running as root")


def missing_tools():
    return {tool: pkg for tool, pkg in REQUIRED_TOOLS.items() if shutil.which(tool) is None}


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
    banner.banner()
    banner.section("environment check")

    check_platform()
    check_root()

    missing = missing_tools()
    if not missing:
        banner.ok("all required tools found (aircrack-ng)")
        return

    packages = sorted(set(missing.values()))
    banner.warn("missing tools: " + ", ".join(sorted(missing)))
    banner.info("provided by package(s): " + ", ".join(packages))

    choice = banner.prompt("install missing dependencies now? [Y/n]")
    if choice.strip().lower() not in ("", "y", "yes"):
        banner.error("DeauthWave needs these tools to run. install them and try again.")
        raise SystemExit(1)

    if not install_packages(packages):
        banner.error("automatic install failed — install manually: sudo apt install " + " ".join(packages))
        raise SystemExit(1)

    still_missing = missing_tools()
    if still_missing:
        banner.error("still missing after install: " + ", ".join(still_missing))
        raise SystemExit(1)

    banner.ok("dependencies installed")
