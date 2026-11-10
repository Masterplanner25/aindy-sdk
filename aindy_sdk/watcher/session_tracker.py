"""
session_tracker.py — Session state machine for A.I.N.D.Y. Watcher.

State machine:
    IDLE ──(work confirmed after confirmation_delay)──► WORKING
    WORKING ──(distraction > distraction_timeout)──► DISTRACTED
    WORKING ──(idle detected)──► IDLE
    DISTRACTED ──(work detected > recovery_delay)──► RECOVERING
    DISTRACTED ──(idle)──► IDLE
    RECOVERING ──(work confirmed)──► WORKING
    RECOVERING ──(distraction)──► DISTRACTED
    RECOVERING ──(idle)──► IDLE

Contract:
  - Pure state machine — no external service calls, no DB, no HTTP
  - All emitted events are returned as a list from update() and stop()
  - Caller is responsible for forwarding events to signal_emitter

Time accounting (FR-65):
  - Focus time is the time BETWEEN samples spent working, credited one interval per sample.
    (1.x before 1.2.0 added the whole time since entering WORKING on every poll, so a
    session's focused_seconds and focus_score were inflated.)
  - A distraction is timed from its own first sample, not from when WORKING began.
  - A session that ends on input idle ends at the last input: duration and focus stop there.
  - session_ended carries ``end_reason``: ``idle`` (lock screen, no window), ``input_idle``
    (no keyboard or mouse for the threshold) or ``stopped`` (the watcher stopped).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List, Optional

from aindy_sdk.watcher.classifier import ActivityType, ClassificationResult


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class SessionState(str, Enum):
    IDLE = "idle"
    CONFIRMING_WORK = "confirming_work"   # transient: building towards WORKING
    WORKING = "working"
    DISTRACTED = "distracted"
    RECOVERING = "recovering"             # transient: building back towards WORKING


@dataclass
class SessionEvent:
    signal_type: str    # session_started | session_ended | distraction_detected |
                        # focus_achieved | context_switch | heartbeat
    session_id: str
    timestamp: str      # ISO 8601 UTC
    app_name: str
    window_title: str
    activity_type: str
    metadata: dict = field(default_factory=dict)


class SessionTracker:
    """
    Tracks session state and emits structured events on transitions.

    Parameters
    ----------
    confirmation_delay : float
        Seconds of continuous WORK activity required to transition IDLE → WORKING.
    distraction_timeout : float
        Seconds of continuous non-WORK activity before WORKING → DISTRACTED.
    recovery_delay : float
        Seconds of continuous WORK activity in RECOVERING state before → WORKING.
    heartbeat_interval : float
        Seconds between heartbeat signals while in WORKING or DISTRACTED state.
    """

    def __init__(
        self,
        confirmation_delay: float = 30.0,
        distraction_timeout: float = 60.0,
        recovery_delay: float = 30.0,
        heartbeat_interval: float = 300.0,  # 5 minutes
    ) -> None:
        self._confirmation_delay = confirmation_delay
        self._distraction_timeout = distraction_timeout
        self._recovery_delay = recovery_delay
        self._heartbeat_interval = heartbeat_interval

        self._state: SessionState = SessionState.IDLE
        self._session_id: str = ""
        self._session_start: Optional[datetime] = None
        self._state_since: datetime = _now_utc()    # when current state was entered
        self._focused_seconds: float = 0.0         # accumulated focus time in session
        self._total_seconds: float = 0.0           # total session time
        self._last_heartbeat: Optional[datetime] = None
        self._last_result: Optional[ClassificationResult] = None
        self._last_update: Optional[datetime] = None        # when the previous sample came
        self._since_last: float = 0.0                       # seconds since that sample
        self._distraction_since: Optional[datetime] = None  # first distraction sample in WORKING
        # Focus credited this session, as (start, end) intervals, so a session ending at the
        # last input can drop what was credited after it.
        self._focus_spans: List[tuple] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def session_id(self) -> str:
        return self._session_id

    def update(self, result: ClassificationResult, now: Optional[datetime] = None) -> List[SessionEvent]:
        """
        Process a new classification sample. Returns zero or more SessionEvents.

        Parameters
        ----------
        result : ClassificationResult
            The latest classification from classifier.classify().
        now : datetime, optional
            Override current time (for testing). Uses UTC now if omitted.
        """
        if now is None:
            now = _now_utc()

        events: List[SessionEvent] = []
        elapsed_in_state = (now - self._state_since).total_seconds()
        self._since_last = (
            max(0.0, (now - self._last_update).total_seconds()) if self._last_update else 0.0
        )
        self._last_update = now

        # --- Context switch detection (same session, different category) ---
        context_switch_event = self._check_context_switch(result, now)
        if context_switch_event:
            events.append(context_switch_event)

        # --- State transitions ---
        match self._state:
            case SessionState.IDLE:
                events.extend(self._handle_idle(result, elapsed_in_state, now))
            case SessionState.CONFIRMING_WORK:
                events.extend(self._handle_confirming_work(result, elapsed_in_state, now))
            case SessionState.WORKING:
                events.extend(self._handle_working(result, elapsed_in_state, now))
            case SessionState.DISTRACTED:
                events.extend(self._handle_distracted(result, elapsed_in_state, now))
            case SessionState.RECOVERING:
                events.extend(self._handle_recovering(result, elapsed_in_state, now))

        # --- Heartbeat ---
        heartbeat = self._maybe_heartbeat(result, now)
        if heartbeat:
            events.append(heartbeat)

        self._last_result = result
        return events

    def stop(self, now: Optional[datetime] = None) -> List[SessionEvent]:
        """The watcher is stopping: end an open session (``end_reason: stopped``).

        Returns ``[session_ended]`` when a session was open, else ``[]``. The tracker is IDLE
        afterwards. The event names the last app sampled.
        """
        if now is None:
            now = _now_utc()
        last = self._last_result or ClassificationResult(
            activity_type=ActivityType.IDLE, confidence=1.0, matched_rule="stopped",
            app_name="", window_title="",
        )
        events = self._close_session(last, now, reason="stopped")
        self._transition_to(SessionState.IDLE, now)
        return events

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    def _handle_idle(
        self, result: ClassificationResult, elapsed: float, now: datetime
    ) -> List[SessionEvent]:
        if result.activity_type == ActivityType.WORK:
            self._transition_to(SessionState.CONFIRMING_WORK, now)
        return []

    def _handle_confirming_work(
        self, result: ClassificationResult, elapsed: float, now: datetime
    ) -> List[SessionEvent]:
        if result.activity_type != ActivityType.WORK:
            # Not sustained — back to IDLE
            self._transition_to(SessionState.IDLE, now)
            return []
        if elapsed >= self._confirmation_delay:
            # Work confirmed
            self._session_id = str(uuid.uuid4())
            self._session_start = now
            self._focused_seconds = 0.0
            self._total_seconds = 0.0
            self._focus_spans = []
            self._last_heartbeat = now
            self._transition_to(SessionState.WORKING, now)
            return [self._make_event("session_started", result, now)]
        return []

    def _handle_working(
        self, result: ClassificationResult, elapsed: float, now: datetime
    ) -> List[SessionEvent]:
        events: List[SessionEvent] = []

        if result.activity_type == ActivityType.IDLE:
            events.extend(self._close_session(result, now))
            self._transition_to(SessionState.IDLE, now)
            return events

        self._total_seconds += self._since_last
        if result.activity_type in (ActivityType.DISTRACTION, ActivityType.COMMUNICATION):
            if self._distraction_since is None:
                self._distraction_since = now
            distracted = (now - self._distraction_since).total_seconds()
            if distracted >= self._distraction_timeout:
                events.append(
                    self._make_event(
                        "distraction_detected",
                        result,
                        now,
                        metadata={
                            "elapsed_distracted_seconds": round(distracted, 1),
                            "distraction_category": result.matched_rule,
                        },
                    )
                )
                self._transition_to(SessionState.DISTRACTED, now)
        else:
            # Active work: credit the interval since the previous sample, once.
            self._distraction_since = None
            if self._since_last > 0:
                self._focused_seconds += self._since_last
                self._focus_spans.append((now.timestamp() - self._since_last, now.timestamp()))

        return events

    def _handle_distracted(
        self, result: ClassificationResult, elapsed: float, now: datetime
    ) -> List[SessionEvent]:
        events: List[SessionEvent] = []

        if result.activity_type == ActivityType.IDLE:
            events.extend(self._close_session(result, now))
            self._transition_to(SessionState.IDLE, now)
            return events

        if result.activity_type == ActivityType.WORK:
            self._transition_to(SessionState.RECOVERING, now)

        return events

    def _handle_recovering(
        self, result: ClassificationResult, elapsed: float, now: datetime
    ) -> List[SessionEvent]:
        events: List[SessionEvent] = []

        if result.activity_type == ActivityType.IDLE:
            events.extend(self._close_session(result, now))
            self._transition_to(SessionState.IDLE, now)
            return events

        if result.activity_type in (ActivityType.DISTRACTION, ActivityType.COMMUNICATION):
            self._transition_to(SessionState.DISTRACTED, now)
            return events

        if result.activity_type == ActivityType.WORK and elapsed >= self._recovery_delay:
            events.append(
                self._make_event(
                    "focus_achieved",
                    result,
                    now,
                    metadata={"recovery_seconds": round(elapsed, 1)},
                )
            )
            self._transition_to(SessionState.WORKING, now)

        return events

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _transition_to(self, new_state: SessionState, now: datetime) -> None:
        self._state = new_state
        self._state_since = now
        self._distraction_since = None

    def _focused_until(self, end: float) -> float:
        """Focus credited at or before ``end`` (a POSIX timestamp)."""
        return sum(max(0.0, min(stop, end) - start) for start, stop in self._focus_spans)

    def _close_session(
        self, result: ClassificationResult, now: datetime, reason: Optional[str] = None
    ) -> List[SessionEvent]:
        if not self._session_id or self._session_start is None:
            return []
        if reason is None:
            reason = "input_idle" if result.matched_rule == "input_idle" else "idle"
        end = now
        if reason == "input_idle" and result.idle_seconds:
            # The session ended at the last input, not when the threshold noticed it.
            end = max(self._session_start, now - timedelta(seconds=result.idle_seconds))
        duration = (end - self._session_start).total_seconds()
        focused = min(self._focused_until(end.timestamp()), duration)
        focus_score = round(focused / duration, 3) if duration > 0 else 0.0
        event = self._make_event(
            "session_ended",
            result,
            end,
            metadata={
                "duration_seconds": round(duration, 1),
                "focused_seconds": round(focused, 1),
                "focus_score": focus_score,
                "end_reason": reason,
            },
        )
        self._session_id = ""
        self._session_start = None
        self._focused_seconds = 0.0
        self._total_seconds = 0.0
        self._focus_spans = []
        return [event]

    def _check_context_switch(
        self, result: ClassificationResult, now: datetime
    ) -> Optional[SessionEvent]:
        """Detect category change within the same active session."""
        if self._state not in (SessionState.WORKING, SessionState.DISTRACTED, SessionState.RECOVERING):
            return None
        if self._last_result is None:
            return None
        if result.activity_type == self._last_result.activity_type:
            return None
        if result.app_name == self._last_result.app_name:
            return None
        return self._make_event(
            "context_switch",
            result,
            now,
            metadata={
                "from_app": self._last_result.app_name,
                "from_type": self._last_result.activity_type,
                "to_app": result.app_name,
                "to_type": result.activity_type,
            },
        )

    def _maybe_heartbeat(
        self, result: ClassificationResult, now: datetime
    ) -> Optional[SessionEvent]:
        if self._state not in (SessionState.WORKING, SessionState.DISTRACTED):
            return None
        if self._last_heartbeat is None:
            return None
        if (now - self._last_heartbeat).total_seconds() >= self._heartbeat_interval:
            self._last_heartbeat = now
            return self._make_event(
                "heartbeat",
                result,
                now,
                metadata={"state": self._state},
            )
        return None

    def _make_event(
        self,
        signal_type: str,
        result: ClassificationResult,
        now: datetime,
        metadata: Optional[dict] = None,
    ) -> SessionEvent:
        return SessionEvent(
            signal_type=signal_type,
            session_id=self._session_id,
            timestamp=now.isoformat(),
            app_name=result.app_name,
            window_title=result.window_title,
            activity_type=result.activity_type,
            metadata=metadata or {},
        )
