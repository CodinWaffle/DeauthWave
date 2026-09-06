from utils import banner
from utils.dependencies import ensure_dependencies


def launch_wifi():
    from modules.wifi_deauth import run
    run()


def main():
    banner.banner()
    while True:
        try:
            launch_wifi()
        except banner.BackToMenu:
            banner.info("bye.")
            return

        choice = banner.prompt("press enter to scan again, or 'q' to quit", accent=banner.C.CYAN)
        if choice.lower() in ("q", "quit", "exit"):
            banner.info("bye.")
            return


if __name__ == "__main__":
    try:
        ensure_dependencies()
        input(f"\n{banner.C.MUTED}press enter to continue to DeauthWave...{banner.C.RESET}")
        main()
    except KeyboardInterrupt:
        print()
        banner.warn("aborted")
