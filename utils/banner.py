"""Terminal theming for DeauthWave: colors, banner, and menu rendering."""

import os
import re
import sys

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class BackToMenu(Exception):
    """Raised by a module to unwind back to the DeauthWave main menu instead of exiting."""


class C:
    """ANSI color codes — dark monochrome teal theme: a single hue at rising
    brightness, not a multi-hue spectrum, for a plain black-terminal/hacker
    look rather than a rainbow gradient."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # logo gradient, top -> bottom: same teal hue throughout, just dimmer at
    # the top and brighter at the bottom — deliberately single-hue so it
    # never reads as a multi-color spectrum
    TEAL_DARK = "\033[38;5;23m"
    SKY = "\033[38;5;30m"
    CYAN = "\033[38;5;37m"
    ICE = "\033[38;5;44m"
    WHITE = "\033[38;5;231m"

    ACCENT = "\033[38;5;44m"   # deep-teal accents / borders
    MUTED = "\033[38;5;67m"    # muted steel-blue for secondary text
    WARN = "\033[38;5;208m"
    DANGER = "\033[38;5;196m"
    OK = "\033[38;5;48m"


# full block-letter wordmark, one continuous word — not split across two
# lines, so "DEAUTHWAVE" reads as one name instead of two stacked halves.
# 86 columns wide, so banner() only uses this on a wide-enough terminal
# (see BIG_LOGO_MIN_WIDTH) and falls back to the compact LOGO_LINES below
# on anything narrower, same defensive pattern as everywhere else here.
BIG_LOGO_LINES = [
    r"██████╗ ███████╗ █████╗ ██╗   ██╗████████╗██╗  ██╗ ██╗    ██╗ █████╗ ██╗   ██╗███████╗",
    r"██╔══██╗██╔════╝██╔══██╗██║   ██║╚══██╔══╝██║  ██║ ██║    ██║██╔══██╗██║   ██║██╔════╝",
    r"██║  ██║█████╗  ███████║██║   ██║   ██║   ███████║ ██║ █╗ ██║███████║██║   ██║█████╗  ",
    r"██║  ██║██╔══╝  ██╔══██║██║   ██║   ██║   ██╔══██║ ██║███╗██║██╔══██║╚██╗ ██╔╝██╔══╝  ",
    r"██████╔╝███████╗██║  ██║╚██████╔╝   ██║   ██║  ██║ ╚███╔███╔╝██║  ██║ ╚████╔╝ ███████╗",
    r"╚═════╝ ╚══════╝╚═╝  ╚═╝ ╚═════╝    ╚═╝   ╚═╝  ╚═╝  ╚══╝╚══╝ ╚═╝  ╚═╝  ╚═══╝  ╚══════╝",
]

# single teal hue, dim at the top and brightening toward the bottom
BIG_LOGO_GRADIENT = [C.TEAL_DARK, C.TEAL_DARK, C.SKY, C.CYAN, C.CYAN, C.ICE]

# narrow-terminal fallback: a single compact line, safe down to width()'s floor
LOGO_LINES = [
    r"▂▄▆█   D E A U T H W A V E   █▆▄▂",
]
LOGO_GRADIENT = [C.SKY]

# BIG_LOGO_LINES is 86 columns wide — require a bit more than that so it
# never sits flush against the terminal edge
BIG_LOGO_MIN_WIDTH = 90

TAGLINE = "wi-fi deauthentication toolkit"
GITHUB_LINK = "github.com/CodinWaffle"
LINKEDIN_LINK = "linkedin.com/in/jose-martin-r-imperial-53a2b429a"

# per-module sub-banners: same storm palette, distinct accent so the screen
# is instantly recognizable as "not the main menu anymore" — just one line,
# since the big wordmark above already carries the app's branding and a
# second wave-bracketed heading right under it read as two stacked logos
MODULE_THEMES = {
    "wifi": {
        "accent": C.CYAN,
        "subtitle": "WIFI DEAUTH · access point discovery & deauthentication",
    },
}


def width(default=72):
    # os.get_terminal_size() queries the real pty directly, bypassing any stale
    # COLUMNS/LINES env vars that shutil.get_terminal_size() would otherwise
    # trust blindly (common after sudo, tmux, or a resized window/pane) — a
    # stale wider value here makes every centered line wrap unpredictably.
    #
    # the floor here must stay BELOW any realistic terminal width: a floor
    # that's higher than a genuinely narrow terminal forces every centered
    # line wider than the terminal itself, which overflows and wraps mid-word
    # exactly like the bug this function exists to prevent.
    try:
        return max(40, min(os.get_terminal_size(sys.__stdout__.fileno()).columns, 90))
    except OSError:
        return default


def clear():
    # \033[2J clears the visible screen, \033[3J clears scrollback, \033[H homes the cursor
    print("\033[2J\033[3J\033[H", end="", flush=True)


def hr(char="─", color=C.MUTED):
    print(f"{color}{char * width()}{C.RESET}")


def _print_logo_and_links():
    """Shared by banner() and module_banner(): the big/compact wordmark, tagline,
    and the GitHub/LinkedIn links box. Returns the terminal width used, so
    callers can keep centering any lines they print after this."""
    w = width()
    lines, gradient = (BIG_LOGO_LINES, BIG_LOGO_GRADIENT) if w >= BIG_LOGO_MIN_WIDTH else (LOGO_LINES, LOGO_GRADIENT)
    for line, shade in zip(lines, gradient):
        print(f"{shade}{C.BOLD}{line.center(w)}{C.RESET}")
    print(f"{C.MUTED}{TAGLINE.center(w)}{C.RESET}")
    print()
    box(
        [
            f"{C.WHITE}{C.BOLD}GitHub  {C.RESET}{C.MUTED}»{C.RESET} {C.ICE}{GITHUB_LINK}{C.RESET}",
            f"{C.WHITE}{C.BOLD}LinkedIn{C.RESET}{C.MUTED}»{C.RESET} {C.ICE}{LINKEDIN_LINK}{C.RESET}",
        ],
        title="connect",
        accent=C.ACCENT,
        w=w,
    )
    return w


def banner():
    clear()
    _print_logo_and_links()
    print()
    hr()


def module_banner(module):
    """Clear the screen and show the sub-banner for a specific module (wifi),
    reusing the same wordmark + links block as the environment check screen."""
    theme = MODULE_THEMES[module]
    accent = theme["accent"]
    clear()
    w = _print_logo_and_links()
    print()
    print(f"{accent}{C.BOLD}{theme['subtitle'].center(w)}{C.RESET}")
    print()
    hr(color=accent)


def section(title, accent=None):
    print(f"\n{accent or C.ACCENT}{C.BOLD}▸ {title}{C.RESET}")


def prompt(label="select an option", accent=None):
    accent = accent or C.ACCENT
    return input(f"{C.CYAN}{C.BOLD}deauthwave{C.RESET}{C.MUTED} ❯ {C.RESET}{label} {accent}» {C.RESET}").strip()


def menu(options, label="select an option", accent=None):
    """
    Render a numbered menu.
    options: list of (key, label, description) tuples
    """
    print()
    for key, opt_label, desc in options:
        key_tag = f"{accent or C.ACCENT}{C.BOLD}[{key}]{C.RESET}"
        label_txt = f"{C.WHITE}{opt_label}{C.RESET}"
        desc_txt = f"{C.MUTED}  · {desc}{C.RESET}" if desc else ""
        print(f"  {key_tag} {label_txt}{desc_txt}")
    print()
    return prompt(label, accent=accent)


def info(msg):
    print(f"{C.SKY}[i]{C.RESET} {msg}")


def ok(msg):
    print(f"{C.OK}[✓]{C.RESET} {msg}")


def warn(msg):
    print(f"{C.WARN}[!]{C.RESET} {msg}")


def error(msg):
    print(f"{C.DANGER}[✗]{C.RESET} {msg}")


def countdown(seconds, label="starting"):
    import time
    for i in range(seconds, 0, -1):
        print(f"\r{C.WARN}[*] {label} in {i}...{C.RESET}   ", end="", flush=True)
        time.sleep(1)
    print(f"\r{C.OK}[*] go.{C.RESET}                        ")


SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


def spinner_frame(tick, accent=None):
    accent = accent or C.ACCENT
    return f"{accent}{C.BOLD}{SPINNER_FRAMES[tick % len(SPINNER_FRAMES)]}{C.RESET}"


def progress_bar(elapsed, total, bar_width=32, accent=None):
    """Render a filled/empty block progress bar with a percentage, e.g. '████░░░░  42%'."""
    accent = accent or C.ACCENT
    ratio = min(1.0, max(0.0, elapsed / total)) if total > 0 else 1.0
    filled = int(bar_width * ratio)
    bar = "█" * filled + "░" * (bar_width - filled)
    pct = int(ratio * 100)
    return f"{accent}{bar}{C.RESET} {C.MUTED}{pct:3d}%{C.RESET}"


def visible_len(s):
    return len(_ANSI_RE.sub("", s))


def _truncate_visible(s, n):
    """Truncate s to at most n visible characters without cutting an ANSI code in half."""
    out = []
    seen = 0
    i = 0
    while i < len(s) and seen < n:
        m = _ANSI_RE.match(s, i)
        if m:
            out.append(m.group())
            i = m.end()
        else:
            out.append(s[i])
            seen += 1
            i += 1
    return "".join(out) + C.RESET


def box(lines, title=None, accent=None, w=None):
    """Print a bordered box around a list of (possibly ANSI-colored) lines.
    Every line is padded or truncated to fit exactly inside the border, so
    content can never spill outside it regardless of terminal-width quirks."""
    accent = accent or C.ACCENT
    w = w or width()
    inner = w - 4  # "│ " + content + " │"

    top = f"╭─ {title} " if title else "╭"
    top += "─" * max(0, w - visible_len(top) - 1) + "╮"
    print(f"{accent}{top}{C.RESET}")

    for line in lines:
        vlen = visible_len(line)
        if vlen > inner:
            line = _truncate_visible(line, inner)
            vlen = inner
        pad = inner - vlen
        print(f"{accent}│{C.RESET} {line}{' ' * pad} {accent}│{C.RESET}")

    print(f"{accent}╰{'─' * (w - 2)}╯{C.RESET}")


if __name__ == "__main__":
    banner()
    section("main menu")
    choice = menu(
        [
            ("1", "WiFi Deauth", "target a wireless access point"),
            ("2", "Exit", "quit DeauthWave"),
        ]
    )
    print(f"\nyou picked: {choice}")
