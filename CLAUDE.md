# CLAUDE.md

Guidance for Claude Code in this repository. Keep it short: rules and pointers, not history. The history is in
`CHANGELOG.md` and the runtime's docs.

## What this repo is

`aindy-sdk` is the Python client for the **A.I.N.D.Y. runtime** (PyPI `aindy-sdk`, import `aindy_sdk`). It has two parts:

- **The API client** (`AINDYClient`). Every call goes over HTTP to a runtime. Most go through `POST /platform/syscall`;
  `client.nodus` uses `/platform/nodus/*` and `client.sandbox` uses `GET /health/sandbox`. It is stdlib only, with no
  runtime dependencies, so keep it that way.
- **The watcher** (`aindy_sdk/watcher/`), a process that runs **on a user's own machine**. It samples the active window,
  classifies activity, and posts signals to `/watcher/signals`.

## Its place in the ecosystem

Part of the Masterplan Infinite Weave ecosystem, by Shawn Knight. The repos below sit side by side under `C:\dev\`.

| Repo | What it is | Relation to this one |
|---|---|---|
| `aindy-runtime` | The server: syscall kernel, flows, memory, agents, Nodus execution, auth. PyPI `aindy-runtime` | **The contract owner.** This SDK is a client of its HTTP surface |
| `aindy-apps-monolith` | The A.I.N.D.Y. application, built as plugins on the runtime | Declares `aindy-sdk>=1.0,<2.0` as a dependency, though no import of it was found in its code (2026-11-07). A breaking change here reaches it on its next install, so keep `1.x` backward compatible |
| `aindy-ui-kit` | Shared React components, npm `@aindy/ui-kit` | Unrelated to this SDK |
| `nodus-lang` and the `nodus-*` repos | The Nodus scripting language and its libraries | `client.nodus` sends Nodus source to the runtime, which runs it |

**The runtime owns the wire contract, and this repo follows it.** The source of truth is
`aindy-runtime/docs/runtime/SDK_CONTRACT.md`, along with the runtime's syscall schemas and request models. If they
disagree with this SDK, the SDK is wrong until the runtime says otherwise.

**Repos talk through docs, not messages.** The runtime records what it needs from this SDK in
`aindy-runtime/docs/handoffs/` (for example `SDK_HANDOFF_1_0_0_wire_mismatches.md`) and in its changelog. Record the answer
in this repo's changelog and PR.

## Rules that bite

- **`tests/test_wire_contract.py` validates every payload against the runtime's own schemas.** It installs `aindy-runtime`
  from the `test` extra. This test exists because three wrong payload shapes stayed green for months while the tests only
  checked what the SDK sent. Any new call needs a case here, not just a unit test of the SDK's own output.
- **Two keys, two meanings, never interchangeable:**
  - `X-Platform-Key` is a user's own key (`aindy_...`). The API client sends this, and so does the watcher when
    `AINDY_WATCHER_KEY` is set.
  - `X-API-Key` is the deployment's **shared secret**, and it can act for **any user**. It is for services only. Never tell a
    user to install it on their machine, and never fall back to it silently when a user key is missing.
- **A feature that needs a newer runtime is opt-in**, and the README and changelog name the minimum runtime version.
- **The repo is public.** Security problems go to private vulnerability reporting (`SECURITY.md`), never into an issue,
  a PR or a commit message.
- Lint is `ruff check . --config ruff.toml`, which is exactly what CI runs. There is no formatter run.

## Commands

```bash
pip install -e ".[test]"         # installs aindy-runtime too, for the contract test
pytest tests/ -q                 # what CI's sdk-contracts runs
ruff check . --config ruff.toml  # what CI's lint runs
python -m build && twine check dist/*
```

## Releasing

1. A PR bumps `aindy_sdk/_version.py` and moves `## Unreleased` in `CHANGELOG.md` under a version heading, leaving a fresh
   `## Unreleased`. Use semver: an additive, opt-in feature is a minor version.
2. Once it's merged and CI is green on `main`, push an annotated tag `vX.Y.Z` on the merge commit. That runs `publish.yml`:
   tag check, lint, build, TestPyPI, then **PyPI behind the `production` environment, which the owner approves**, then the
   GitHub release.
3. Then verify: PyPI lists the version, the GitHub release isn't a draft, and the published wheel holds the change.

`main` is protected: changes go through a PR, and `lint` and `sdk-contracts` must pass.
