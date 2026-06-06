from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aindy_sdk.watcher.classifier import ActivityType, ClassificationResult, classify
from aindy_sdk.watcher.session_tracker import SessionState, SessionTracker
from aindy_sdk.watcher.window_detector import WindowInfo


def _win(app: str, title: str = "") -> WindowInfo:
    return WindowInfo(app_name=app, window_title=title)


# ---------------------------------------------------------------------------
# classifier
# ---------------------------------------------------------------------------

def test_classifier_returns_idle_for_none_window():
    result = classify(None)
    assert result.activity_type == ActivityType.IDLE
    assert result.confidence == 1.0
    assert result.matched_rule == "no_active_window"


def test_classifier_identifies_work_process():
    result = classify(_win("code", "main.py"))
    assert result.activity_type == ActivityType.WORK


def test_classifier_identifies_distraction_process():
    result = classify(_win("spotify", "Playlist"))
    assert result.activity_type == ActivityType.DISTRACTION


def test_classifier_identifies_distraction_via_browser_title():
    result = classify(_win("chrome", "YouTube - trending"))
    assert result.activity_type == ActivityType.DISTRACTION


def test_classifier_identifies_communication_process():
    result = classify(_win("slack", "General"))
    assert result.activity_type == ActivityType.COMMUNICATION


def test_classifier_returns_unknown_for_unrecognised_app():
    result = classify(_win("xyzunknownapp999", "window"))
    assert result.activity_type == ActivityType.UNKNOWN
    assert result.confidence == 0.5


# ---------------------------------------------------------------------------
# session_tracker
# ---------------------------------------------------------------------------

def test_session_tracker_starts_in_idle_with_no_session():
    tracker = SessionTracker()
    assert tracker.state == SessionState.IDLE
    assert tracker.session_id == ""


def test_session_tracker_enters_confirming_work_on_first_work_sample():
    tracker = SessionTracker(confirmation_delay=5.0)
    work = ClassificationResult(
        activity_type=ActivityType.WORK,
        confidence=0.9,
        matched_rule="work_process:code",
        app_name="code",
        window_title="main.py",
    )
    t0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    events = tracker.update(work, now=t0)
    assert tracker.state == SessionState.CONFIRMING_WORK
    assert events == []


def test_session_tracker_emits_session_started_after_confirmation_delay():
    tracker = SessionTracker(confirmation_delay=5.0)
    work = ClassificationResult(
        activity_type=ActivityType.WORK,
        confidence=0.9,
        matched_rule="work_process:code",
        app_name="code",
        window_title="main.py",
    )
    t0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    tracker.update(work, now=t0)
    events = tracker.update(work, now=t0 + timedelta(seconds=6))
    assert tracker.state == SessionState.WORKING
    assert any(e.signal_type == "session_started" for e in events)
    assert tracker.session_id != ""
