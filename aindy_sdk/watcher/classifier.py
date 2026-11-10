"""
classifier.py — Activity classification from window/process information.

Maps (app_name, window_title) → ActivityType.

Rules are evaluated in priority order: IDLE → DISTRACTION → WORK → COMMUNICATION → UNKNOWN.
Pattern matching is case-insensitive and uses substring matching on app_name and window_title.

The lists are configurable (FR-65): see ``AppRules.from_env``. An app you name yourself is
checked before every built-in list, so naming a built-in distraction as work wins.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional

from aindy_sdk.watcher.window_detector import WindowInfo


class ActivityType(str, Enum):
    WORK = "work"
    COMMUNICATION = "communication"
    DISTRACTION = "distraction"
    IDLE = "idle"
    UNKNOWN = "unknown"


@dataclass
class ClassificationResult:
    activity_type: ActivityType
    confidence: float  # 0.0 – 1.0
    matched_rule: str  # human-readable label for the rule that matched
    app_name: str
    window_title: str
    #: Seconds since the last keyboard or mouse input when sampled; None when unknown.
    idle_seconds: Optional[float] = None


# ---------------------------------------------------------------------------
# Classification rule sets
# (process_patterns, title_patterns) — all lowercase, substring or regex)
# ---------------------------------------------------------------------------

_IDLE_PROCESSES: frozenset[str] = frozenset(
    [
        "screensaver",
        "loginwindow",
        "lockapp",          # Windows lock screen
        "logonui",          # Windows logon UI
        "systemuiserver",   # macOS menu bar daemon (no foreground app)
    ]
)

_WORK_PROCESSES: frozenset[str] = frozenset(
    [
        # Editors / IDEs
        "cursor",
        "code",             # VS Code
        "code - insiders",
        "pycharm",
        "pycharm64",
        "idea",
        "idea64",
        "webstorm",
        "webstorm64",
        "phpstorm",
        "goland",
        "clion",
        "rider",
        "rubymine",
        "datagrip",
        "vim",
        "nvim",
        "neovim",
        "sublime_text",
        "atom",
        "emacs",
        "notepad++",
        "zed",
        # Terminals
        "terminal",
        "iterm",
        "iterm2",
        "warp",
        "windows terminal",
        "windowsterminal",
        "cmd",
        "powershell",
        "pwsh",
        "bash",
        "zsh",
        "alacritty",
        "kitty",
        "hyper",
        "wezterm",
        "konsole",
        "gnome-terminal",
        "xterm",
        # Runtime / build tools
        "python",
        "python3",
        "node",
        "npm",
        "cargo",
        "rustc",
        "go",
        "java",
        "javac",
        "gradle",
        "mvn",
        "make",
        "cmake",
        # Version control
        "git",
        "sourcetree",
        "gitkraken",
        "fork",
        # Design / docs
        "figma",
        "sketch",
        "affinity",
        "notion",
        # Productivity
        "obsidian",
        "logseq",
        "roamresearch",
    ]
)

_COMMUNICATION_PROCESSES: frozenset[str] = frozenset(
    [
        "slack",
        "teams",
        "discord",
        "zoom",
        "meet",
        "webex",
        "skype",
        "outlook",
        "thunderbird",
        "mail",
        "airmail",
        "mimestream",
        "spark",
        "superhuman",
        "telegram",
        "signal",
        "whatsapp",
        "messenger",
        "imessage",
        "messages",
        "facetime",
    ]
)

_DISTRACTION_PROCESSES: frozenset[str] = frozenset(
    [
        "youtube",
        "netflix",
        "twitch",
        "hulu",
        "disneyplus",
        "primevideo",
        "spotify",
        "music",           # macOS Music.app
        "vlc",
        "mpv",
        "steam",
        "epicgameslauncher",
        "roblox",
        "minecraft",
        "origin",
        "battlenet",
        "gog galaxy",
    ]
)

# Title patterns indicating distraction even when in a browser
_DISTRACTION_TITLE_PATTERNS: list[re.Pattern] = [
    re.compile(r"youtube", re.IGNORECASE),
    re.compile(r"netflix", re.IGNORECASE),
    re.compile(r"twitch", re.IGNORECASE),
    re.compile(r"\breddit\b", re.IGNORECASE),
    re.compile(r"twitter|x\.com", re.IGNORECASE),
    re.compile(r"tiktok", re.IGNORECASE),
    re.compile(r"instagram", re.IGNORECASE),
    re.compile(r"facebook", re.IGNORECASE),
    re.compile(r"\bsteam\b.*store", re.IGNORECASE),
    re.compile(r"hacker news", re.IGNORECASE),
]

_BROWSER_PROCESSES: frozenset[str] = frozenset(
    [
        "chrome",
        "chromium",
        "firefox",
        "safari",
        "edge",
        "msedge",
        "opera",
        "brave browser",
        "brave",
        "vivaldi",
        "arc",
    ]
)


# ---------------------------------------------------------------------------
# Configurable lists (FR-65)
# ---------------------------------------------------------------------------

#: (env suffix, ActivityType it adds to, attribute on AppRules)
_LIST_ENV = (
    ("IDLE_APPS", ActivityType.IDLE, "idle"),
    ("DISTRACTION_APPS", ActivityType.DISTRACTION, "distraction"),
    ("WORK_APPS", ActivityType.WORK, "work"),
    ("COMMUNICATION_APPS", ActivityType.COMMUNICATION, "communication"),
)


def _split(value: str) -> tuple[list[str], list[str]]:
    """``"a, -b ,c"`` → (added [a, c], removed [b]); lowercase, blanks dropped."""
    added, removed = [], []
    for item in (value or "").split(","):
        item = item.strip().lower()
        if item.startswith("-") and item[1:].strip():
            removed.append(item[1:].strip())
        elif item:
            added.append(item)
    return added, removed


@dataclass(frozen=True)
class AppRules:
    """The lists ``classify`` matches against. ``AppRules()`` is the built-in set."""

    idle: frozenset = _IDLE_PROCESSES
    distraction: frozenset = _DISTRACTION_PROCESSES
    work: frozenset = _WORK_PROCESSES
    communication: frozenset = _COMMUNICATION_PROCESSES
    browser: frozenset = _BROWSER_PROCESSES
    distraction_titles: tuple = tuple(_DISTRACTION_TITLE_PATTERNS)
    #: What you named yourself, checked before every built-in list: ((ActivityType, names), ...).
    custom: tuple = ()
    #: Window-title substrings you named as distraction in a browser, checked before the built-ins.
    custom_distraction_titles: tuple = field(default=())

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "AppRules":
        """Read the lists from the environment, each a comma-separated list of names.

        ``AINDY_WATCHER_WORK_APPS``, ``_DISTRACTION_APPS``, ``_COMMUNICATION_APPS``, ``_IDLE_APPS``
        and ``_BROWSER_APPS`` take app (process) names. ``AINDY_WATCHER_DISTRACTION_TITLES`` takes
        window-title text that marks a browser tab as a distraction. A plain name is added and
        checked before the built-in lists; ``-name`` removes a built-in entry (for titles, the
        built-in pattern that matches that text). Matching is case-insensitive substring.
        """
        env = os.environ if environ is None else environ
        values = {}
        custom = []
        for suffix, activity, attr in _LIST_ENV:
            added, removed = _split(env.get(f"AINDY_WATCHER_{suffix}", ""))
            values[attr] = frozenset(getattr(cls, attr) - set(removed))
            if added:
                custom.append((activity, frozenset(added)))
        added, removed = _split(env.get("AINDY_WATCHER_BROWSER_APPS", ""))
        values["browser"] = frozenset((_BROWSER_PROCESSES - set(removed)) | set(added))
        added, removed = _split(env.get("AINDY_WATCHER_DISTRACTION_TITLES", ""))
        values["distraction_titles"] = tuple(
            p for p in _DISTRACTION_TITLE_PATTERNS if not any(p.search(r) for r in removed)
        )
        return cls(**values, custom=tuple(custom), custom_distraction_titles=tuple(added))

    def counts(self) -> dict:
        """How many names each list holds, for the startup log."""
        return {
            "custom": sum(len(names) for _, names in self.custom),
            "work": len(self.work), "distraction": len(self.distraction),
            "communication": len(self.communication), "idle": len(self.idle),
            "browser": len(self.browser),
            "distraction_titles": len(self.distraction_titles) + len(self.custom_distraction_titles),
        }


_DEFAULT_RULES = AppRules()


def apply_input_idle(
    result: ClassificationResult, idle_seconds: Optional[float], threshold: float
) -> ClassificationResult:
    """Record the input-idle reading on ``result``, and make it IDLE once it reaches ``threshold``.

    ``threshold <= 0`` turns the override off; ``idle_seconds`` None (unknown) never makes a
    sample idle. A sample already IDLE keeps its own rule.
    """
    result.idle_seconds = idle_seconds
    if (
        threshold > 0 and idle_seconds is not None and idle_seconds >= threshold
        and result.activity_type != ActivityType.IDLE
    ):
        return ClassificationResult(
            activity_type=ActivityType.IDLE,
            confidence=1.0,
            matched_rule="input_idle",
            app_name=result.app_name,
            window_title=result.window_title,
            idle_seconds=idle_seconds,
        )
    return result


def classify(window: Optional[WindowInfo], rules: Optional[AppRules] = None) -> ClassificationResult:
    """
    Classify the current activity from a WindowInfo snapshot.

    Returns ClassificationResult with IDLE when window is None. ``rules`` defaults to the
    built-in lists.
    """
    rules = rules or _DEFAULT_RULES
    if window is None:
        return ClassificationResult(
            activity_type=ActivityType.IDLE,
            confidence=1.0,
            matched_rule="no_active_window",
            app_name="",
            window_title="",
        )

    app = window.app_name.lower().strip()
    title = window.window_title.lower().strip()

    # Remove file extension for matching (.exe, .app)
    app_base = re.sub(r"\.(exe|app|bin)$", "", app)

    def _result(activity: ActivityType, confidence: float, rule: str) -> ClassificationResult:
        return ClassificationResult(
            activity_type=activity, confidence=confidence, matched_rule=rule,
            app_name=app, window_title=window.window_title,
        )

    is_browser = any(b in app_base or b in app for b in rules.browser)

    # --- What you named yourself, before every built-in list ---
    for activity, names in rules.custom:
        for pat in names:
            if pat in app_base or pat in app:
                return _result(activity, 0.95, f"custom_{activity.value}_process:{pat}")
    if is_browser:
        for text in rules.custom_distraction_titles:
            if text in title:
                return _result(ActivityType.DISTRACTION, 0.9, f"custom_distraction_title:{text}")

    # --- IDLE ---
    for pat in rules.idle:
        if pat in app_base or pat in app:
            return ClassificationResult(
                activity_type=ActivityType.IDLE,
                confidence=0.95,
                matched_rule=f"idle_process:{pat}",
                app_name=app,
                window_title=window.window_title,
            )

    # --- DISTRACTION (process name) ---
    for pat in rules.distraction:
        if pat in app_base or pat in app:
            return ClassificationResult(
                activity_type=ActivityType.DISTRACTION,
                confidence=0.9,
                matched_rule=f"distraction_process:{pat}",
                app_name=app,
                window_title=window.window_title,
            )

    # --- DISTRACTION (browser + title) ---
    if is_browser:
        for pattern in rules.distraction_titles:
            if pattern.search(title) or pattern.search(window.window_title):
                return ClassificationResult(
                    activity_type=ActivityType.DISTRACTION,
                    confidence=0.85,
                    matched_rule=f"distraction_title:{pattern.pattern}",
                    app_name=app,
                    window_title=window.window_title,
                )

    # --- WORK ---
    for pat in rules.work:
        if pat in app_base or pat in app:
            return ClassificationResult(
                activity_type=ActivityType.WORK,
                confidence=0.9,
                matched_rule=f"work_process:{pat}",
                app_name=app,
                window_title=window.window_title,
            )

    # --- COMMUNICATION ---
    for pat in rules.communication:
        if pat in app_base or pat in app:
            return ClassificationResult(
                activity_type=ActivityType.COMMUNICATION,
                confidence=0.9,
                matched_rule=f"communication_process:{pat}",
                app_name=app,
                window_title=window.window_title,
            )

    # --- UNKNOWN ---
    return ClassificationResult(
        activity_type=ActivityType.UNKNOWN,
        confidence=0.5,
        matched_rule="no_match",
        app_name=app,
        window_title=window.window_title,
    )
