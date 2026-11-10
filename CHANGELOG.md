# Changelog

## Unreleased

_Nothing yet._

## 1.2.0 — 2026-11-10

### Added — the watcher ends a session when you walk away, and when it stops (FR-65)

- **Idle detection.** With no keyboard or mouse input for `AINDY_WATCHER_IDLE_TIMEOUT` seconds (default 300; `0` turns it off), the session ends, at the last input. Before this, a session ended only on a lock screen, so a working day without a lock never sent `session_ended`, and the app's focus score never saw it. It reads `GetLastInputInfo` on Windows, `HIDIdleTime` on macOS, and `xprintidle` on Linux X11; where none is available the watcher says so at startup and behaves as before.
- **`session_ended` on a clean stop.** Ctrl+C or SIGTERM now ends an open session before the final flush. Before this, stopping the watcher dropped the session.
- **`metadata.end_reason`** on `session_ended`: `input_idle`, `idle` (lock screen or no window) or `stopped`. The existing keys are unchanged.
- **Your own app lists**: `AINDY_WATCHER_WORK_APPS`, `_DISTRACTION_APPS`, `_COMMUNICATION_APPS`, `_IDLE_APPS`, `_BROWSER_APPS` and `AINDY_WATCHER_DISTRACTION_TITLES`. A name you add is checked before the built-in lists; `-name` removes a built-in. `classify()` takes an optional `rules=` (`AppRules`); called without it, it behaves as before.
- **An `aindy-watcher` console script**, and `python -m aindy_sdk.watcher`. The old `python -m aindy_sdk.watcher.watcher` still works.

### Fixed — the watcher's focus numbers were wrong

- **`focused_seconds` and `focus_score` were inflated.** Each poll added the whole time since the session entered WORKING, not the time since the previous poll, so ten minutes of work at the default 5-second poll was recorded as about 605 minutes focused, a focus score of about 60. Each poll now adds only the interval since the previous one. Scores from 1.1.0 and earlier are not comparable with these.
- **A distraction fired too early.** The distraction timeout was compared with how long the session had been WORKING, not with how long the distraction had lasted, so after a minute of work a single sample of a distracting app sent `distraction_detected` at once. It is now timed from the distraction's first sample.

## 1.1.0 — 2026-11-07

### Added — the watcher can use your own key

- **`AINDY_WATCHER_KEY`** holds a key you mint with `POST /watcher/keys`, and is sent as `X-Platform-Key`. It needs runtime 2.31.4 or later. That key acts only for you and works only on the watcher routes.
- **`AINDY_API_KEY` still works** and is used when `AINDY_WATCHER_KEY` is unset. It is the deployment's shared secret and can act for any user, so keep it to services and don't install it on a user's machine.

## 1.0.1 — 2026-09-21

### Fixed — three wire mismatches the SDK's own tests could not see

- **`client.events.emit()` sent `{"type": …}`; the runtime's `sys.v1.event.emit` requires
  `event_type`.** It 422'd on every call, against every runtime release since 1.0.0 shipped. Now
  sends `event_type`.
- **`client.nodus.upload_script()` sent `source`; the runtime's `NodusScriptUpload` model names
  the body `content`.** 422 on every call. Now sends `content` (the Python parameter is still
  `source`).
- **`client.memory.tree()`'s docstring promised `data["flat"]`; no runtime handler produces
  it** (`sys.v1.memory.tree` returns `tree`, `node_count`, `path`). Docstring corrected; flatten
  client-side if you need depth-first order.
- `client.memory.write()`'s docstring now says that `extra` is merged by the runtime rather than
  declared by the schema — it works by the absence of `additionalProperties: false`.
- (`client.flow.run()` sending `initial_state` shipped at `94b5a44` and reaches PyPI with this
  release.)

### Added — a wire-contract test against the runtime's own schemas

`tests/test_wire_contract.py` captures every payload the SDK sends and validates it with the
runtime's `validate_payload` / request models. `aindy-runtime` is now a `[test]` dependency for
that reason. The SDK's other tests mock the dispatcher and can only pin what the SDK sends —
which is how the shapes above stayed green while broken. Found by the runtime running its
tutorials against the published 1.0.0 (`SDK_HANDOFF_1_0_0_wire_mismatches.md`).

## Unreleased (before 1.0.1)

### Fixed — `client.execution.get()` now backed by the runtime (2026-07-05)

- `client.execution.get()` dispatches `sys.v1.execution.get`, which had no
  handler registered in `aindy-runtime` — the call failed live with an
  "unknown syscall" error while the SDK's own unit tests (which mock the
  dispatcher) stayed green. The runtime now registers the syscall
  (capability `execution.read`, read-only, tenant-scoped). Requires an
  `aindy-runtime` build that includes `sys.v1.execution.get`; JWT callers get
  the `execution.read` capability by default, platform API keys must carry the
  `execution.read` scope.

### Added — Watcher client process (2026-06-03)

- **`aindy_sdk/watcher/`**: New subpackage containing the A.I.N.D.Y. Watcher
  client process. The watcher runs on the user's machine, polls the active OS
  window, classifies activity (WORK / COMMUNICATION / DISTRACTION / IDLE), tracks
  session state transitions, and emits batched signals to the runtime's
  `POST /watcher/signals` endpoint.

  Run with:
  ```
  python -m aindy_sdk.watcher.watcher
  python -m aindy_sdk.watcher.watcher --dry-run
  ```

  Modules: `window_detector`, `classifier`, `session_tracker`, `signal_emitter`,
  `config`, `watcher` (main loop). Signal emission uses stdlib `urllib.request`
  — no new external dependencies introduced.

  Optional platform dependencies for enhanced window detection:
  - macOS: `pyobjc-framework-AppKit`, `pyobjc-framework-Quartz`
  - Linux: `xdotool` (system package)
  - Windows: `ctypes` (stdlib, no install required)
  - Fallback: `psutil` (any platform, best-effort)

---

## 1.0.0 — 2026-05-25

Initial PyPI release. Universal interface SDK targeting both local-install
(`aindy-runtime` on operator infrastructure) and cloud-hosted deployment
contexts. Switching between local and cloud requires only a `base_url` change.
Extracted as a standalone package from aindy-apps-monolith; stdlib-only,
no runtime dependency on aindy-runtime internals.

### Changed — Universal interface role documented (2026-05-25)

- **`README.md`**: Named `aindy-sdk` as the local+cloud bridge — the universal
  interface SDK that works against both a locally-installed runtime (operator
  owns infrastructure) and a cloud-hosted runtime (provider owns infrastructure).
  Updated description, added cloud-hosted usage comment in the code example,
  and clarified that switching deployment context requires only a `base_url`
  change.
