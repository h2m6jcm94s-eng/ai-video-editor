"""Helper for Python workers to report user-facing errors to the API."""

import os
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_API_URL = os.environ.get("API_URL", "http://localhost:4000")
_INTERNAL_TOKEN = os.environ.get("INTERNAL_API_TOKEN", "")


class UserEventReporter:
    """Reports user events to the API's internal endpoint."""

    def __init__(self, api_url: Optional[str] = None, token: Optional[str] = None) -> None:
        self.api_url = (api_url or _API_URL).rstrip("/")
        self.token = token or _INTERNAL_TOKEN
        if not self.token:
            logger.warning("INTERNAL_API_TOKEN not set; user event reporting will fail")

    def report(
        self,
        user_id: str,
        code: str,
        message: str,
        details: Optional[dict] = None,
        route: Optional[str] = None,
    ) -> bool:
        """Report a user event. Returns True if accepted."""
        if not self.token:
            logger.debug("Skipping user event report — no INTERNAL_API_TOKEN")
            return False

        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(
                    f"{self.api_url}/api/internal/user-events",
                    headers={"x-internal-token": self.token},
                    json={
                        "userId": user_id,
                        "code": code,
                        "message": message,
                        "details": details,
                        "route": route,
                    },
                )
            if resp.status_code == 200:
                return True
            logger.warning("User event report rejected: %s %s", resp.status_code, resp.text)
            return False
        except Exception as e:
            logger.warning("User event report failed: %s", e)
            return False

    async def areport(
        self,
        user_id: str,
        code: str,
        message: str,
        details: Optional[dict] = None,
        route: Optional[str] = None,
    ) -> bool:
        """Async version of report."""
        if not self.token:
            logger.debug("Skipping user event report — no INTERNAL_API_TOKEN")
            return False

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{self.api_url}/api/internal/user-events",
                    headers={"x-internal-token": self.token},
                    json={
                        "userId": user_id,
                        "code": code,
                        "message": message,
                        "details": details,
                        "route": route,
                    },
                )
            if resp.status_code == 200:
                return True
            logger.warning("User event report rejected: %s %s", resp.status_code, resp.text)
            return False
        except Exception as e:
            logger.warning("User event report failed: %s", e)
            return False


def report_user_event(
    user_id: str,
    code: str,
    message: str,
    details: Optional[dict] = None,
    route: Optional[str] = None,
) -> bool:
    """Convenience function using default reporter."""
    return UserEventReporter().report(user_id, code, message, details, route)
