# Changelog

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
