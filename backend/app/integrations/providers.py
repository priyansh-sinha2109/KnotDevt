"""Official, fixed-host read-only adapters. No arbitrary fetch URLs or LLM calls."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import urlencode

import httpx

from app.core.config import settings

PROVIDERS = ("github", "slack", "jira")
SCOPES = {
    "github": "",
    "slack": "channels:read,channels:history",
    "jira": "read:jira-work read:jira-user offline_access",
}


class RemoteError(Exception):
    def __init__(self, status: str, message: str, delay: int = 60):
        self.status, self.message, self.delay = status, message, delay
        super().__init__(message)


def configured(provider: str) -> bool:
    c = settings()
    return bool(
        c.integration_encryption_key
        and getattr(c, provider + "_client_id", "")
        and getattr(c, provider + "_client_secret", None)
    )


def callback(provider: str) -> str:
    return (
        settings().integration_callback_base.rstrip("/") + "/" + provider + "/callback"
    )


def authorize_url(provider: str, state: str) -> str:
    base = {
        "github": "https://github.com/login/oauth/authorize",
        "slack": "https://slack.com/oauth/v2/authorize",
        "jira": "https://auth.atlassian.com/authorize",
    }[provider]
    params = {
        "client_id": getattr(settings(), provider + "_client_id"),
        "state": state,
        "redirect_uri": callback(provider),
        "scope": SCOPES[provider],
    }
    if provider == "jira":
        params.update(
            audience="api.atlassian.com", response_type="code", prompt="consent"
        )
    if provider == "slack":
        params["user_scope"] = "channels:read,channels:history"
    return base + "?" + urlencode(params)


def request(method: str, url: str, **kwargs: Any) -> Any:
    if not url.startswith(
        (
            "https://api.github.com/",
            "https://github.com/login/oauth/",
            "https://slack.com/api/",
            "https://auth.atlassian.com/",
            "https://api.atlassian.com/",
        )
    ):
        raise ValueError("Untrusted connector endpoint")
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            result = client.request(method, url, **kwargs)
    except httpx.HTTPError:
        raise RemoteError("sync_failed", "Provider could not be reached.") from None
    if result.status_code == 429 or (
        result.status_code == 403 and result.headers.get("x-ratelimit-remaining") == "0"
    ):
        try:
            delay = max(60, min(86400, int(result.headers.get("retry-after", "60"))))
        except ValueError:
            delay = 60
        raise RemoteError(
            "rate_limited",
            "Provider rate limit reached; sync will resume later.",
            delay,
        )
    if result.status_code in (401, 403, 404):
        raise RemoteError(
            "needs_reauthorization"
            if result.status_code == 401
            else "permission_denied",
            "Provider access is unavailable. Reauthorize the connection.",
        )
    if result.status_code >= 300:
        raise RemoteError("sync_failed", "Provider rejected the request.")
    data = result.json()
    if isinstance(data, dict) and data.get("ok") is False:
        code = data.get("error")
        raise RemoteError(
            "rate_limited"
            if code == "ratelimited"
            else "needs_reauthorization"
            if code in ("token_revoked", "invalid_auth", "token_expired")
            else "permission_denied",
            "Slack did not permit this request.",
        )
    return data


def exchange(provider: str, code: str) -> dict[str, Any]:
    c = settings()
    payload = {
        "client_id": getattr(c, provider + "_client_id"),
        "client_secret": getattr(c, provider + "_client_secret").get_secret_value(),
        "code": code,
        "redirect_uri": callback(provider),
    }
    url = {
        "github": "https://github.com/login/oauth/access_token",
        "slack": "https://slack.com/api/oauth.v2.access",
        "jira": "https://auth.atlassian.com/oauth/token",
    }[provider]
    if provider == "jira":
        payload["grant_type"] = "authorization_code"
    data = request(
        "POST",
        url,
        headers={"Accept": "application/json"},
        **({"json": payload} if provider == "jira" else {"data": payload}),
    )
    if not data.get("access_token"):
        raise RemoteError(
            "needs_reauthorization", "Authorization did not return a credential."
        )
    if provider == "slack" and data.get("authed_user", {}).get("access_token"):
        data.update(data["authed_user"])
    data["obtained_at"] = datetime.now(UTC).timestamp()
    return cast(dict[str, Any], data)


def headers(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token, "Accept": "application/json"}


def identities(provider: str, token: dict[str, Any]) -> list[dict[str, str]]:
    h = headers(token["access_token"])
    if provider == "github":
        # GitHub App user tokens only see installations accessible to both app and user.
        data = request(
            "GET",
            "https://api.github.com/user/installations",
            headers=h,
            params={"per_page": 100},
        )
        return [
            {"id": str(item["id"]), "name": item["account"]["login"]}
            for item in data["installations"]
        ]
    if provider == "slack":
        team = token["team"]
        return [{"id": team["id"], "name": team.get("name", team["id"])}]
    data = request(
        "GET", "https://api.atlassian.com/oauth/token/accessible-resources", headers=h
    )
    return [
        {"id": item["id"], "name": item["name"], "url": item["url"]}
        for item in data
        if "read:jira-work" in item.get("scopes", [])
    ]


def resources(provider: str, token: str, external: str) -> list[dict[str, str]]:
    h = headers(token)
    result = []
    cursor = ""
    for page in range(1, 11):
        if provider == "github":
            data = request(
                "GET",
                f"https://api.github.com/user/installations/{external}/repositories",
                headers=h,
                params={"per_page": 100, "page": page},
            )
            rows = [
                {"id": str(x["id"]), "name": x["full_name"]}
                for x in data["repositories"]
            ]
            more = page * 100 < data["total_count"]
        elif provider == "slack":
            data = request(
                "GET",
                "https://slack.com/api/conversations.list",
                headers=h,
                params={
                    "types": "public_channel",
                    "exclude_archived": True,
                    "limit": 100,
                    "cursor": cursor if page > 1 else "",
                },
            )
            rows = [
                {"id": x["id"], "name": "#" + x["name"]}
                for x in data["channels"]
                if x.get("is_member") and not x.get("is_private")
            ]
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            more = bool(cursor)
        else:
            data = request(
                "GET",
                f"https://api.atlassian.com/ex/jira/{external}/rest/api/3/project/search",
                headers=h,
                params={"startAt": (page - 1) * 100, "maxResults": 100},
            )
            rows = [
                {"id": x["id"], "name": x["key"] + " · " + x["name"]}
                for x in data["values"]
            ]
            more = not data.get("isLast", True)
        result.extend(rows)
        if not more:
            break
    return result


def rich_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(rich_text(x) for x in value)
    if not isinstance(value, dict):
        return ""
    text = value.get("text", "") + rich_text(value.get("content", []))
    if value.get("type") == "hardBreak" or value.get("type") in {
        "paragraph",
        "heading",
        "listItem",
        "codeBlock",
    }:
        text += "\n"
    return str(text)


def fetch_page(
    provider: str,
    token: str,
    external: str,
    resource: dict[str, str],
    cursor: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], bool]:
    """One bounded page; persisted cursor advances only with committed imports."""
    h = headers(token)
    rows: list[dict[str, Any]] = []
    now = datetime.now(UTC).isoformat()
    if provider == "github":
        # Resolve repository by stable ID and reconfirm current access before each page.
        repo = request(
            "GET", "https://api.github.com/repositories/" + resource["id"], headers=h
        )
        full = repo["full_name"]
        import re

        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", full):
            raise RemoteError("permission_denied", "Invalid repository identity.")
        endpoint = cursor.get("endpoint", "metadata")
        if endpoint == "metadata":
            return (
                [
                    {
                        "id": "repository:" + str(repo["id"]),
                        "text": json.dumps(repo, ensure_ascii=False),
                        "author": repo.get("owner", {}).get("login", "Unknown author"),
                        "url": repo["html_url"],
                        "at": repo["updated_at"],
                        "type": "comment",
                    }
                ],
                {"endpoint": "issues", "page": 1},
                False,
            )
        if endpoint == "discussions":
            if not repo.get("has_discussions"):
                return [], {}, True
            owner, name = full.split("/")
            result = request(
                "POST",
                "https://api.github.com/graphql",
                headers=h,
                json={
                    "query": """query($owner:String!,$name:String!,$after:String){
                  repository(owner:$owner,name:$name){discussions(first:20,after:$after){
                    nodes{id title body url updatedAt author{login}}
                    pageInfo{hasNextPage endCursor}
                  }}}""",
                    "variables": {
                        "owner": owner,
                        "name": name,
                        "after": cursor.get("after"),
                    },
                },
            )
            if result.get("errors"):
                raise RemoteError(
                    "permission_denied", "Discussions access is unavailable."
                )
            discussions = result["data"]["repository"]["discussions"]
            rows = [
                {
                    "id": "discussion:" + item["id"],
                    "text": item["title"] + "\n" + item["body"],
                    "author": (item.get("author") or {}).get("login", "Unknown author"),
                    "url": item["url"],
                    "at": item["updatedAt"],
                    "type": "comment",
                }
                for item in discussions["nodes"]
            ]
            info = discussions["pageInfo"]
            return rows, {**cursor, "after": info["endCursor"]}, not info["hasNextPage"]
        data = request(
            "GET",
            f"https://api.github.com/repos/{full}/{endpoint}",
            headers=h,
            params={
                "state": "all",
                "per_page": 30,
                "page": cursor.get("page", 1),
                **(
                    {"since": cursor["since"]}
                    if cursor.get("since") and endpoint == "issues"
                    else {}
                ),
            },
        )
        for item in data:
            is_commit = endpoint == "commits"
            author = (item.get("user") or item.get("author") or {}).get(
                "login", "Unknown author"
            )
            content = json.dumps(item, ensure_ascii=False)
            rows.append(
                {
                    "id": endpoint + ":" + str(item.get("id", item.get("sha"))),
                    "text": content,
                    "author": author,
                    "url": item["html_url"],
                    "at": item.get(
                        "updated_at",
                        item.get("commit", {}).get("author", {}).get("date", now),
                    ),
                    "type": "implementation"
                    if is_commit
                    else "comment"
                    if "comments" in endpoint
                    else "task",
                }
            )
        if len(data) == 30:
            return rows, {**cursor, "page": int(cursor.get("page", 1)) + 1}, False
        endpoints = [
            "issues",
            "issues/comments",
            "pulls",
            "pulls/comments",
            "commits",
            "discussions",
        ]
        if endpoint != endpoints[-1]:
            return (
                rows,
                {
                    **cursor,
                    "endpoint": endpoints[endpoints.index(endpoint) + 1],
                    "page": 1,
                },
                False,
            )
        return rows, {"since": now}, True
    if provider == "slack":
        channel = request(
            "GET",
            "https://slack.com/api/conversations.info",
            headers=h,
            params={"channel": resource["id"]},
        )["channel"]
        if (
            channel.get("is_private")
            or not channel.get("is_member")
            or channel.get("is_im")
        ):
            raise RemoteError(
                "permission_denied",
                "Channel is not an authorized public member channel.",
            )
        pending = list(cursor.get("threads", []))
        thread = pending[0] if pending else None
        data = request(
            "GET",
            "https://slack.com/api/conversations.replies"
            if thread
            else "https://slack.com/api/conversations.history",
            headers=h,
            params={
                "channel": resource["id"],
                "limit": 15,
                "oldest": cursor.get("oldest", "0"),
                "cursor": cursor.get("thread_next", "")
                if thread
                else cursor.get("next", ""),
                **({"ts": thread} if thread else {}),
            },
        )
        for item in data["messages"]:
            if item.get("subtype") in (
                "message_deleted",
                "channel_join",
                "channel_leave",
            ):
                continue
            permalink = request(
                "GET",
                "https://slack.com/api/chat.getPermalink",
                headers=h,
                params={"channel": resource["id"], "message_ts": item["ts"]},
            )["permalink"]
            rows.append(
                {
                    "id": resource["id"] + ":" + item["ts"],
                    "text": (item.get("text", "") or "[Message has no text]")
                    + "\n"
                    + json.dumps(
                        {
                            "thread_ts": item.get("thread_ts"),
                            "edited": item.get("edited"),
                            "files": [
                                {
                                    key: file.get(key)
                                    for key in ("id", "name", "mimetype", "permalink")
                                }
                                for file in item.get("files", [])
                            ],
                        },
                        sort_keys=True,
                    ),
                    "author": item.get("user", "Unknown author"),
                    "url": permalink,
                    "at": datetime.fromtimestamp(
                        float(item.get("edited", {}).get("ts", item["ts"])), UTC
                    ).isoformat(),
                    "type": "message",
                }
            )
        nxt = data.get("response_metadata", {}).get("next_cursor", "")
        if thread:
            pending = pending if nxt else pending[1:]
            result = {**cursor, "threads": pending, "thread_next": nxt}
            return rows, result, not pending and not cursor.get("next")
        pending = [x["ts"] for x in data["messages"] if x.get("reply_count", 0)]
        return (
            rows,
            {**cursor, "next": nxt, "threads": pending},
            not bool(nxt or pending),
        )
    pending = list(cursor.get("issues", []))
    if pending:
        issue = pending[0]
        phase = str(cursor.get("detail", "comment"))
        detail = request(
            "GET",
            f"https://api.atlassian.com/ex/jira/{external}/rest/api/3/issue/"
            f"{issue['id']}/{phase}",
            headers=h,
            params={"startAt": cursor.get("start", 0), "maxResults": 30},
        )
        entries = (
            detail.get("comments", [])
            if phase == "comment"
            else detail.get("values", [])
        )
        for value in entries:
            rows.append(
                {
                    "id": issue["id"] + ":" + phase + ":" + value["id"],
                    "text": rich_text(value.get("body"))
                    + "\n"
                    + json.dumps(value, ensure_ascii=False),
                    "author": value.get("author", {}).get(
                        "displayName", "Unknown author"
                    ),
                    "url": cursor["site_url"].rstrip("/") + "/browse/" + issue["key"],
                    "at": value.get("updated", value.get("created", now)),
                    "type": "comment",
                }
            )
        start = int(cursor.get("start", 0)) + len(entries)
        if start < detail.get("total", 0) and entries:
            return rows, {**cursor, "start": start}, False
        if phase == "comment":
            return rows, {**cursor, "detail": "changelog", "start": 0}, False
        pending = pending[1:]
        return (
            rows,
            {**cursor, "issues": pending, "detail": "comment", "start": 0},
            not pending and not cursor.get("next"),
        )
    data = request(
        "GET",
        f"https://api.atlassian.com/ex/jira/{external}/rest/api/3/search/jql",
        headers=h,
        params={
            "jql": 'project = "' + resource["id"] + '" ORDER BY updated ASC',
            "maxResults": 30,
            "fields": (
                "summary,description,assignee,reporter,status,priority,"
                "issuetype,created,updated,issuelinks"
            ),
            **({"nextPageToken": cursor["next"]} if cursor.get("next") else {}),
        },
    )
    for item in data["issues"]:
        fields = item["fields"]
        rows.append(
            {
                "id": item["id"],
                "text": item["key"]
                + ": "
                + fields["summary"]
                + "\n"
                + rich_text(fields.get("description"))
                + "\n"
                + json.dumps(fields, ensure_ascii=False),
                "author": (fields.get("reporter") or {}).get(
                    "displayName", "Unknown author"
                ),
                "url": cursor["site_url"].rstrip("/") + "/browse/" + item["key"],
                "at": fields["updated"],
                "type": "task",
            }
        )
    nxt = data.get("nextPageToken", "")
    pending = [{"id": item["id"], "key": item["key"]} for item in data["issues"]]
    return rows, {**cursor, "next": nxt, "issues": pending}, not bool(nxt or pending)


def stable_id(connection: str, resource: str, object_id: str) -> str:
    return (
        "ext-"
        + hashlib.sha256(
            (connection + ":" + resource + ":" + object_id).encode()
        ).hexdigest()
    )
