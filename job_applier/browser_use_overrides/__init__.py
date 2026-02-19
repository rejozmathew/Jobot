"""Local browser-use runtime patches used by auto-job-applier."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def apply_browser_use_overrides() -> None:
    """Apply all local browser-use monkey patches."""
    try:
        from .gif import install as install_gif_patch

        install_gif_patch()
    except Exception as exc:
        logger.warning("Failed to apply browser-use GIF override: %s", exc)

