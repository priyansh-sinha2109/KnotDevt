"""Explicit, bounded public discovery. Results require separate evidence import."""

import hashlib
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import settings


def research(
    query: str, domains: list[str], *, permitted: bool = False
) -> dict[str, Any]:
    if not permitted:
        raise ValueError("Public research requires explicit project permission")
    if not 1 <= len(query) <= 500 or not 1 <= len(domains) <= 5:
        raise ValueError("Research request exceeds limits")
    for domain in domains:
        if not re.fullmatch(r"[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+", domain):
            raise ValueError("Invalid public research domain")
    credential = settings().tavily_api_key
    if credential is None:
        raise ValueError("Public research credential unavailable")
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        response = client.post(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {credential.get_secret_value()}"},
            json={"query": query, "include_domains": domains, "max_results": 3},
        )
        response.raise_for_status()
        results = response.json().get("results", [])
    return {
        "provider": "tavily",
        "access_policy": "public_preview",
        "retrieved_at": datetime.now(UTC).isoformat(),
        "verified": False,
        "requires_authorized_import": True,
        "results": [
            {
                "url": item["url"],
                "content": str(item.get("content", ""))[:4000],
                "content_sha256": hashlib.sha256(
                    str(item.get("content", ""))[:4000].encode()
                ).hexdigest(),
            }
            for item in results[:3]
            if urlsplit(item.get("url", "")).scheme == "https"
            and urlsplit(item["url"]).hostname in domains
        ],
    }
