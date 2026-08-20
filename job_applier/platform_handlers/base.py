"""Platform handler base abstractions and shared browser helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class HandlerResult(str, Enum):
    """Terminal/intermediate outcomes emitted by deterministic handlers."""

    SUBMITTED = "SUBMITTED"
    PROGRESSED = "PROGRESSED"
    NEEDS_LLM = "NEEDS_LLM"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass(slots=True)
class HandlerOutcome:
    """Structured deterministic handler response."""

    result: HandlerResult
    state: str = ""
    message: str = ""
    steps: list[str] = field(default_factory=list)
    blocker_code: str = ""
    handoff_context: str = ""


TraceHook = Callable[[dict[str, Any]], None]


def env_flag(name: str, default: bool = False) -> bool:
    value = str(os.environ.get(name, "")).strip().lower()
    if not value:
        return default
    return value not in {"0", "false", "no", "off"}


async def safe_navigate(page_or_session: Any, url: str, settle_ms: int = 2500) -> tuple[bool, str]:
    """Navigate using actor-page-compatible signatures (no wait_until kwarg)."""
    if page_or_session is None:
        return False, "no-active-page"
    if hasattr(page_or_session, "navigate_to"):
        try:
            await page_or_session.navigate_to(str(url or ""), new_tab=False)
            if settle_ms > 0 and hasattr(page_or_session, "get_current_page"):
                try:
                    current = await page_or_session.get_current_page()
                    if current is not None:
                        await current.wait_for_timeout(int(settle_ms))
                except Exception:
                    pass
            return True, "ok"
        except Exception as exc:
            if hasattr(page_or_session, "get_current_page"):
                try:
                    current = await page_or_session.get_current_page()
                    if current is not None:
                        try:
                            await current.goto(str(url or ""))
                        except TypeError:
                            await current.navigate(str(url or ""))
                        if settle_ms > 0:
                            try:
                                await current.wait_for_timeout(int(settle_ms))
                            except Exception:
                                pass
                        return True, "ok-fallback-goto"
                except Exception:
                    pass
            return False, f"navigate_to-failed:{exc}"
    page = page_or_session
    try:
        await page.goto(str(url or ""))
    except TypeError:
        try:
            await page.navigate(str(url or ""))
        except Exception as exc:  # pragma: no cover - safety net for runtime differences
            return False, f"navigate-failed:{exc}"
    except Exception as exc:
        return False, f"goto-failed:{exc}"

    if settle_ms > 0:
        try:
            await page.wait_for_timeout(int(settle_ms))
        except Exception:
            pass
    return True, "ok"


class BasePlatformHandler:
    """Base class for deterministic platform handlers."""

    platform_name = "generic"

    def __init__(
        self,
        *,
        browser_session: Any,
        profile: dict[str, Any] | None,
        job_url: str,
        trace_hook: Optional[TraceHook] = None,
    ) -> None:
        self.browser_session = browser_session
        self.profile = profile or {}
        self.job_url = str(job_url or "")
        self.trace_hook = trace_hook

    @classmethod
    def can_handle(cls, url: str) -> bool:
        return False

    async def run(self) -> HandlerOutcome:  # pragma: no cover - interface method
        raise NotImplementedError

    async def recover(self, loop_context: dict[str, Any]) -> HandlerOutcome:
        return HandlerOutcome(
            result=HandlerResult.NEEDS_LLM,
            state="recover",
            message="No deterministic recovery available for this platform.",
            handoff_context=str(loop_context or ""),
        )

    def trace(self, event: str, **payload: Any) -> None:
        if not self.trace_hook:
            return
        data = {"event": event, "platform": self.platform_name}
        data.update(payload)
        try:
            self.trace_hook(data)
        except Exception:
            # Never fail job flow due to tracing callback issues.
            pass
