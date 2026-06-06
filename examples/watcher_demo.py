"""
A.I.N.D.Y. Watcher dry-run demo.

Runs the watcher for 30 seconds in dry-run mode — no HTTP requests are sent.
Signals are logged to the console so you can see the activity classification
and session state machine in action without a live runtime.

Usage:
    python examples/watcher_demo.py

To run against a live runtime instead, set environment variables and omit --dry-run:
    AINDY_WATCHER_API_URL=http://localhost:8000 \
    AINDY_API_KEY=aindy_... \
    python -m aindy_sdk.watcher.watcher
"""
import logging
import os
import threading
import time

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("watcher_demo")

# Force dry-run before importing watcher modules so the env var is set before
# config.load() reads it.
os.environ["AINDY_WATCHER_DRY_RUN"] = "true"
os.environ.setdefault("AINDY_WATCHER_POLL_INTERVAL", "2")
os.environ.setdefault("AINDY_WATCHER_CONFIRMATION_DELAY", "5")
os.environ.setdefault("AINDY_WATCHER_DISTRACTION_TIMEOUT", "10")
os.environ.setdefault("AINDY_WATCHER_LOG_LEVEL", "DEBUG")

from aindy_sdk.watcher import config
from aindy_sdk.watcher.watcher import run

DEMO_DURATION_SECONDS = 30


def _stop_after(cfg_ref, seconds: float) -> None:
    """Send SIGINT to this process after `seconds` to trigger graceful shutdown."""
    time.sleep(seconds)
    logger.info("Demo timer expired after %ss — requesting shutdown", seconds)
    import signal
    import os as _os
    _os.kill(_os.getpid(), signal.SIGINT)


def main() -> None:
    cfg = config.load()

    logger.info("=== A.I.N.D.Y. Watcher dry-run demo ===")
    logger.info("  dry_run:            %s", cfg.dry_run)
    logger.info("  poll_interval:      %.1fs", cfg.poll_interval)
    logger.info("  confirmation_delay: %.1fs", cfg.confirmation_delay)
    logger.info("  distraction_timeout: %.1fs", cfg.distraction_timeout)
    logger.info("  flush_interval:     %.1fs", cfg.flush_interval)
    logger.info("")
    logger.info("Signals will be logged here. No HTTP requests will be sent.")
    logger.info("Stopping automatically after %ss.", DEMO_DURATION_SECONDS)
    logger.info("Press Ctrl+C at any time to stop early.")
    logger.info("")

    errors = config.validate(cfg)
    if errors:
        for err in errors:
            logger.error("Config error: %s", err)
        raise SystemExit(1)

    timer = threading.Thread(target=_stop_after, args=(cfg, DEMO_DURATION_SECONDS), daemon=True)
    timer.start()

    run(cfg)

    logger.info("")
    logger.info("=== Demo complete ===")
    logger.info(
        "To run against a live runtime:\n"
        "  AINDY_WATCHER_API_URL=http://localhost:8000 \\\n"
        "  AINDY_API_KEY=aindy_... \\\n"
        "  python -m aindy_sdk.watcher.watcher"
    )


if __name__ == "__main__":
    main()
