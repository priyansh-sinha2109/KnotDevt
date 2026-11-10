import hashlib
import re
from datetime import UTC, datetime

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError

ISSUE_URL = re.compile(
    r"https://github\.com/([A-Za-z0-9-]{1,39})/([A-Za-z0-9_.-]{1,100})/issues/([1-9][0-9]{0,9})"
)
MAX_RESPONSE = 512 * 1024


class GitHubAuthor(BaseModel):
    login: str


class GitHubIssue(BaseModel):
    number: int
    title: str
    user: GitHubAuthor
    created_at: datetime
    updated_at: datetime
    state: str
    state_reason: str | None = None
    assignees: list[GitHubAuthor] = Field(default_factory=list)
    closed_at: datetime | None = None
    body: str | None
    html_url: str
    pull_request: dict[str, object] | None = None


class GitHubSnapshot(BaseModel):
    repository: str
    number: int
    title: str
    author: str
    created_at: datetime
    updated_at: datetime
    state: str
    state_reason: str | None
    assignees: list[str]
    closed_at: datetime | None
    body: str
    original_url: str
    retrieved_at: datetime
    snapshot_sha256: str


def public_issue(reference: str) -> GitHubSnapshot:
    match = ISSUE_URL.fullmatch(reference)
    if not match or match[2] in {".", ".."}:
        raise HTTPException(422, "Choose an original public GitHub issue link")
    owner, repo, number = match.groups()
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"
    try:
        with httpx.stream(
            "GET",
            url,
            timeout=8.0,
            follow_redirects=False,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        ) as response:
            if response.status_code == 404:
                raise HTTPException(404, "Public issue unavailable")
            response.raise_for_status()
            raw = bytearray()
            for chunk in response.iter_bytes():
                if len(raw) + len(chunk) > MAX_RESPONSE:
                    raise HTTPException(413, "Public issue response is too large")
                raw.extend(chunk)
        issue = GitHubIssue.model_validate_json(raw)
    except (httpx.HTTPError, ValidationError):
        raise HTTPException(
            502, "Could not retrieve this public issue from GitHub"
        ) from None
    if (
        issue.pull_request is not None
        or issue.number != int(number)
        or issue.html_url.casefold() != reference.casefold()
    ):
        raise HTTPException(422, "GitHub returned a different issue reference")
    return GitHubSnapshot(
        repository=f"{owner}/{repo}",
        number=issue.number,
        title=issue.title,
        author=issue.user.login,
        created_at=issue.created_at,
        updated_at=issue.updated_at,
        state=issue.state,
        state_reason=issue.state_reason,
        assignees=[item.login for item in issue.assignees],
        closed_at=issue.closed_at,
        body=issue.body or "",
        original_url=issue.html_url,
        retrieved_at=datetime.now(UTC),
        snapshot_sha256=hashlib.sha256(issue.model_dump_json().encode()).hexdigest(),
    )
