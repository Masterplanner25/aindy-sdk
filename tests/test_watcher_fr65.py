"""FR-65: idle detection, session_ended on stop, a correct focus sum, configurable app lists,
and a console script.

The app scores focus from `session_ended` (`duration_seconds`, `focus_score` in its metadata), so
these tests read those keys the way it does.
"""
from __future__ import annotations

import subprocess
import sys
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from aindy_sdk.watcher import classifier, config, idle_detector, watcher
from aindy_sdk.watcher.classifier import ActivityType, AppRules, ClassificationResult, apply_input_idle, classify
from aindy_sdk.watcher.session_tracker import SessionState, SessionTracker
from aindy_sdk.watcher.window_detector import WindowInfo

T0 = datetime(2026, 11, 10, 9, 0, 0, tzinfo=timezone.utc)
STEP = 5


def _r(activity: ActivityType, app: str = "code", rule: str = "", idle: float | None = None) -> ClassificationResult:
    return ClassificationResult(activity_type=activity, confidence=0.9, matched_rule=rule or f"{activity.value}",
                                app_name=app, window_title="", idle_seconds=idle)


WORK = _r(ActivityType.WORK)
DISTRACTION = _r(ActivityType.DISTRACTION, app="spotify")
LOCKED = _r(ActivityType.IDLE, app="lockapp", rule="idle_process:lockapp")


def _started(tracker: SessionTracker) -> datetime:
    """Confirm a session (delay 0): returns the session's start time."""
    tracker.update(WORK, now=T0)
    events = tracker.update(WORK, now=T0)
    assert [e.signal_type for e in events] == ["session_started"]
    return T0


def _feed(tracker: SessionTracker, start: datetime, seconds: int, result=WORK) -> list:
    """One sample every STEP seconds over (start, start + seconds]."""
    events = []
    for t in range(STEP, seconds + 1, STEP):
        events += tracker.update(result, now=start + timedelta(seconds=t))
    return events


def _ended(events) -> dict:
    [ended] = [e for e in events if e.signal_type == "session_ended"]
    return {"at": ended.timestamp, **ended.metadata}


# -- the focus sum -------------------------------------------------------------------------------


def test_focus_is_the_time_spent_working_not_a_running_sum():
    """1.1.0 added the whole time since WORKING began on every poll: 10 minutes of work at a
    5-second poll read as about 605 minutes focused."""
    tracker = SessionTracker(confirmation_delay=0)
    start = _started(tracker)
    _feed(tracker, start, 600)

    ended = _ended(tracker.stop(now=start + timedelta(seconds=600)))

    assert ended["duration_seconds"] == 600.0
    assert ended["focused_seconds"] == 600.0
    assert ended["focus_score"] == 1.0
    assert ended["end_reason"] == "stopped"


def test_distracted_time_is_not_focus():
    tracker = SessionTracker(confirmation_delay=0, distraction_timeout=60)
    start = _started(tracker)
    _feed(tracker, start, 300)                                           # work 0..300
    _feed(tracker, start + timedelta(seconds=300), 30, DISTRACTION)      # 305..330, under the timeout
    _feed(tracker, start + timedelta(seconds=330), 270)                  # work 335..600

    ended = _ended(tracker.stop(now=start + timedelta(seconds=600)))

    # Not credited: the six distraction samples' intervals (300..330). The first work sample
    # after them credits its own interval (330..335).
    assert ended["focused_seconds"] == 570.0
    assert ended["focus_score"] == round(570 / 600, 3)


def test_a_distraction_is_timed_from_its_own_start():
    """1.1.0 compared WORKING's age with the timeout, so after a minute of work a single
    distraction sample fired `distraction_detected` at once."""
    tracker = SessionTracker(confirmation_delay=0, distraction_timeout=60)
    start = _started(tracker)
    _feed(tracker, start, 120)

    first = tracker.update(DISTRACTION, now=start + timedelta(seconds=125))
    assert first == [] or all(e.signal_type != "distraction_detected" for e in first)
    assert tracker.state == SessionState.WORKING

    events = _feed(tracker, start + timedelta(seconds=125), 60, DISTRACTION)
    detected = [e for e in events if e.signal_type == "distraction_detected"]
    assert len(detected) == 1
    assert detected[0].metadata["elapsed_distracted_seconds"] == 60.0
    assert tracker.state == SessionState.DISTRACTED


def test_work_between_distractions_restarts_the_distraction_clock():
    tracker = SessionTracker(confirmation_delay=0, distraction_timeout=60)
    start = _started(tracker)
    events = []
    for t in range(STEP, 300, STEP):  # alternate: never 60s of continuous distraction
        events += tracker.update(DISTRACTION if (t // STEP) % 2 else WORK, now=start + timedelta(seconds=t))
    assert not [e for e in events if e.signal_type == "distraction_detected"]


# -- ending a session ----------------------------------------------------------------------------


def test_a_lock_screen_ends_the_session_with_reason_idle():
    tracker = SessionTracker(confirmation_delay=0)
    start = _started(tracker)
    _feed(tracker, start, 60)
    ended = _ended(tracker.update(LOCKED, now=start + timedelta(seconds=65)))
    assert ended["end_reason"] == "idle"
    assert ended["duration_seconds"] == 65.0


def test_input_idle_ends_the_session_at_the_last_input():
    """No input since t=100; the 300-second threshold notices at t=400. The session must end at
    100, and the 300 seconds of 'work' samples after it (the window stayed on the editor) must not
    count as focus."""
    tracker = SessionTracker(confirmation_delay=0)
    start = _started(tracker)
    _feed(tracker, start, 100)
    for t in range(105, 400, STEP):  # the editor is still in front, nobody is there
        tracker.update(_r(ActivityType.WORK, idle=t - 100), now=start + timedelta(seconds=t))

    noticed = apply_input_idle(_r(ActivityType.WORK), idle_seconds=300, threshold=300)
    ended = _ended(tracker.update(noticed, now=start + timedelta(seconds=400)))

    assert ended["end_reason"] == "input_idle"
    assert ended["at"] == (start + timedelta(seconds=100)).isoformat()
    assert ended["duration_seconds"] == 100.0
    assert ended["focused_seconds"] == 100.0
    assert tracker.state == SessionState.IDLE


def test_stop_ends_an_open_session_and_nothing_otherwise():
    tracker = SessionTracker(confirmation_delay=0)
    assert tracker.stop(now=T0) == []  # control: no session, nothing sent

    start = _started(tracker)
    session = tracker.session_id
    _feed(tracker, start, 30)
    [ended] = tracker.stop(now=start + timedelta(seconds=30))

    assert ended.signal_type == "session_ended"
    assert ended.session_id == session
    assert ended.app_name == "code"
    assert set(ended.metadata) >= {"duration_seconds", "focus_score", "focused_seconds", "end_reason"}
    assert tracker.state == SessionState.IDLE and tracker.session_id == ""
    assert tracker.stop(now=start + timedelta(seconds=31)) == []  # not twice


class _Emitter:
    def __init__(self):
        self.calls = []

    def emit_many(self, events):
        self.calls.append(("emit", [e.signal_type for e in events]))

    def stop(self, drain_timeout):
        self.calls.append(("stop", drain_timeout))


def test_shutdown_sends_session_ended_before_the_final_flush():
    import logging

    tracker = SessionTracker(confirmation_delay=0)
    _started(tracker)
    emitter = _Emitter()

    watcher._shutdown(tracker, emitter, logging.getLogger("t"))

    assert emitter.calls == [("emit", ["session_ended"]), ("stop", 10.0)]


def test_shutdown_still_flushes_when_ending_the_session_fails(monkeypatch):
    import logging

    tracker = SessionTracker(confirmation_delay=0)
    monkeypatch.setattr(tracker, "stop", lambda: 1 / 0)
    emitter = _Emitter()

    watcher._shutdown(tracker, emitter, logging.getLogger("t"))

    assert emitter.calls == [("stop", 10.0)]


# -- idle detection ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "idle,threshold,expected",
    [
        (299.0, 300, ActivityType.WORK),
        (300.0, 300, ActivityType.IDLE),
        (None, 300, ActivityType.WORK),   # unknown is never idle
        (9999.0, 0, ActivityType.WORK),   # 0 turns it off
    ],
)
def test_input_idle_threshold(idle, threshold, expected):
    result = apply_input_idle(_r(ActivityType.WORK), idle, threshold)
    assert result.activity_type == expected
    assert result.idle_seconds == idle
    if expected == ActivityType.IDLE:
        assert result.matched_rule == "input_idle"


def test_a_lock_screen_keeps_its_own_rule_under_input_idle():
    assert apply_input_idle(LOCKED, 9999.0, 300).matched_rule == "idle_process:lockapp"


def test_the_loop_reads_input_idle_only_when_it_is_on(monkeypatch):
    reads = []
    monkeypatch.setattr(watcher, "get_active_window", lambda: WindowInfo(app_name="code", window_title="x"))
    monkeypatch.setattr(idle_detector, "seconds_since_input", lambda: reads.append(1) or 600.0)
    cfg = config.load()

    cfg.idle_timeout = 300
    assert watcher._sample(cfg, AppRules()).activity_type == ActivityType.IDLE
    cfg.idle_timeout = 0
    assert watcher._sample(cfg, AppRules()).activity_type == ActivityType.WORK
    assert len(reads) == 1


def test_idle_detection_never_raises(monkeypatch):
    def boom():
        raise OSError("no display")

    for name in ("_idle_windows", "_idle_macos", "_idle_linux"):
        monkeypatch.setattr(idle_detector, name, boom)
    for system in ("Windows", "Darwin", "Linux", "Plan9"):
        monkeypatch.setattr(idle_detector, "_SYSTEM", system)
        assert idle_detector.seconds_since_input() is None


@pytest.mark.skipif(sys.platform != "win32", reason="GetLastInputInfo is Windows-only")
def test_windows_reads_a_real_idle_time():
    value = idle_detector.seconds_since_input()
    assert value is not None and 0 <= value < 49.8 * 86400


def test_macos_parses_hid_idle_time(monkeypatch):
    class _Out:
        stdout = '    |   "HIDIdleTime" = 12500000000\n'

    monkeypatch.setattr(idle_detector.subprocess, "run", lambda *a, **k: _Out())
    assert idle_detector._idle_macos() == 12.5


def test_idle_timeout_config(monkeypatch):
    monkeypatch.delenv("AINDY_WATCHER_IDLE_TIMEOUT", raising=False)
    assert config.load().idle_timeout == 300.0
    monkeypatch.setenv("AINDY_WATCHER_IDLE_TIMEOUT", "-1")
    assert any("IDLE_TIMEOUT" in e for e in config.validate(config.load()))


# -- configurable app lists ----------------------------------------------------------------------


def _win(app: str, title: str = "") -> WindowInfo:
    return WindowInfo(app_name=app, window_title=title)


def test_a_named_work_app_beats_a_built_in_distraction():
    assert classify(_win("spotify.exe")).activity_type == ActivityType.DISTRACTION  # control
    rules = AppRules.from_env({"AINDY_WATCHER_WORK_APPS": "spotify, blender"})
    assert classify(_win("spotify.exe"), rules).activity_type == ActivityType.WORK
    assert classify(_win("blender.exe"), rules).activity_type == ActivityType.WORK
    assert classify(_win("blender.exe")).activity_type == ActivityType.UNKNOWN  # control


def test_a_minus_removes_a_built_in():
    rules = AppRules.from_env({"AINDY_WATCHER_DISTRACTION_APPS": "-spotify"})
    assert classify(_win("spotify.exe"), rules).activity_type == ActivityType.UNKNOWN
    assert classify(_win("netflix.exe"), rules).activity_type == ActivityType.DISTRACTION


def test_browser_titles_are_configurable():
    rules = AppRules.from_env({
        "AINDY_WATCHER_DISTRACTION_TITLES": "the onion, -reddit",
        "AINDY_WATCHER_BROWSER_APPS": "librewolf",
    })
    assert classify(_win("librewolf", "The Onion - news"), rules).activity_type == ActivityType.DISTRACTION
    assert classify(_win("chrome", "reddit - r/python"), rules).activity_type != ActivityType.DISTRACTION
    assert classify(_win("chrome", "reddit - r/python")).activity_type == ActivityType.DISTRACTION  # control
    assert classify(_win("chrome", "YouTube"), rules).activity_type == ActivityType.DISTRACTION


def test_no_environment_means_the_built_in_lists():
    assert AppRules.from_env({}).counts() == AppRules().counts()


# -- the console script --------------------------------------------------------------------------


def test_the_console_script_is_declared_and_resolves():
    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8"))
    target = project["project"]["scripts"]["aindy-watcher"]
    module, func = target.split(":")
    assert module == "aindy_sdk.watcher.watcher" and callable(getattr(watcher, func))


def test_python_dash_m_runs_the_watcher():
    out = subprocess.run([sys.executable, "-m", "aindy_sdk.watcher", "--help"],
                         capture_output=True, text=True, timeout=60, cwd=Path(__file__).parents[1])
    assert out.returncode == 0, out.stderr
    assert "--dry-run" in out.stdout


def test_classifier_module_still_exports_its_1_x_names():
    """1.x callers import these; keep them."""
    for name in ("classify", "ActivityType", "ClassificationResult"):
        assert hasattr(classifier, name)
