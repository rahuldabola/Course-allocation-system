"""API-key auth dependency for state-changing / expensive endpoints.

Design: a single shared key (`API_KEY`), sent as `X-API-Key`, checked with a
constant-time comparison. Simple by design for a project this size — no user
accounts, sessions, or roles. If `API_KEY` is unset, auth is disabled (open
dev mode) so `docker compose up` keeps working out of the box; set it to
require the header in any shared/deployed environment.
"""
from __future__ import annotations

import hmac

from fastapi import Header, HTTPException

from .config import settings


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    if not settings.api_key:
        return  # auth disabled (no key configured)
    if not x_api_key or not hmac.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key header")
