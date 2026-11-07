# Security

## Reporting a vulnerability

Please report it privately, through
[GitHub's private vulnerability reporting](https://github.com/Masterplanner25/aindy-sdk/security/advisories/new).
Don't open a public issue or pull request for it.

Include the version you tested, what you did, and what you could reach that you shouldn't have.

If the problem is in the server rather than this client, report it to
[`aindy-runtime`](https://github.com/Masterplanner25/aindy-runtime/security/advisories/new) instead. If you're not sure, either
place is fine.

## Supported versions

Fixes ship in a new release and are not backported, so the supported version is the newest one on
[PyPI](https://pypi.org/project/aindy-sdk/).

## Keys

The watcher should run with your own key (`AINDY_WATCHER_KEY`). The deployment's shared `AINDY_API_KEY` can act for any user,
so it belongs on servers only, never on a user's machine.
