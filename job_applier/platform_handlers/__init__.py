"""Platform handler framework and built-in handlers."""

from .base import BasePlatformHandler, HandlerOutcome, HandlerResult, env_flag, safe_navigate
from .registry import create_platform_handler, detect_platform
from .workday import (
    WORKDAY_EXISTING_DATA_CONFLICT_KEYWORDS,
    WORKDAY_EXPERIENCE_FIELD_LOOP_KEYWORDS,
    WORKDAY_REQUIRED_FIELD_LOOP_KEYWORDS,
    WorkdayHandler,
    context_matches,
    is_workday_url,
    month_year_from_value,
    normalize_text,
    run_workday_legacy_create_account,
)

__all__ = [
    "BasePlatformHandler",
    "HandlerOutcome",
    "HandlerResult",
    "WorkdayHandler",
    "create_platform_handler",
    "detect_platform",
    "env_flag",
    "safe_navigate",
    "is_workday_url",
    "context_matches",
    "month_year_from_value",
    "normalize_text",
    "run_workday_legacy_create_account",
    "WORKDAY_EXISTING_DATA_CONFLICT_KEYWORDS",
    "WORKDAY_REQUIRED_FIELD_LOOP_KEYWORDS",
    "WORKDAY_EXPERIENCE_FIELD_LOOP_KEYWORDS",
]
