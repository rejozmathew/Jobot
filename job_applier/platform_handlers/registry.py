"""Platform handler detection and factory helpers."""

from __future__ import annotations

import os
from typing import Any, Optional

from .base import BasePlatformHandler, TraceHook
from .workday import WorkdayHandler
from .greenhouse import GreenhouseHandler

HANDLER_TYPES: tuple[type[BasePlatformHandler], ...] = (WorkdayHandler, GreenhouseHandler)


def detect_platform(url: str) -> str:
    override = os.environ.get("JOB_APPLIER_PLATFORM", "").strip().lower()
    if override in ("workday", "greenhouse", "generic"):
        return override
    for handler_type in HANDLER_TYPES:
        if handler_type.can_handle(url):
            return handler_type.platform_name
    return "generic"


def create_platform_handler(
    *,
    url: str,
    browser_session: Any,
    profile: dict[str, Any] | None,
    trace_hook: Optional[TraceHook] = None,
) -> BasePlatformHandler | None:
    override = os.environ.get("JOB_APPLIER_PLATFORM", "").strip().lower()
    want_greenhouse = override == "greenhouse" or GreenhouseHandler.can_handle(url)
    if want_greenhouse:
        cdp_url = os.environ.get("BROWSER_USE_CDP_URL", "").strip() or "http://127.0.0.1:9222"
        return GreenhouseHandler(
            browser_session=None,   # connect lazily inside run() (async)
            profile=profile,
            job_url=url,
            trace_hook=trace_hook,
            cdp_url=cdp_url,
        )
    for handler_type in HANDLER_TYPES:
        if handler_type.platform_name == "greenhouse":
            continue  # handled above (needs its own CDP session)
        if handler_type.can_handle(url):
            return handler_type(
                browser_session=browser_session,
                profile=profile or {},
                job_url=url,
                trace_hook=trace_hook,
            )
    return None

