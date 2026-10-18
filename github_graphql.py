#!/usr/bin/env python3
"""Retrieve and normalize authenticated GitHub profile statistics.

Only the Python standard library is used. Authentication is read at runtime
from ``GITHUB_TOKEN``/``GH_TOKEN`` or, when neither is present, from
``gh auth token``. Token material is never included in generated data or
error messages.

Current-streak semantics:

* A contribution day has at least one GitHub-recorded contribution.
* "Today" is determined in ``Africa/Lagos``.
* A contribution today starts the backward streak walk from today.
* When today is empty, yesterday may continue the current streak.
* When both today and yesterday are empty, the current streak is zero.
* The calendar must cover every requested local date. A streak reaching the
  first available day is rejected as incomplete rather than underestimated.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo


USERNAME = "macanthonyeke"
LOCAL_TIMEZONE = "Africa/Lagos"
GRAPHQL_ENDPOINT = "https://api.github.com/graphql"
DEFAULT_OUTPUT = Path("assets/github-stats.json")
SNAPSHOT_DAYS = 365


PROFILE_QUERY = """
query Profile($login: String!, $from: DateTime!, $to: DateTime!, $cursor: String) {
  viewer { login }
  user(login: $login) {
    login
    repositories(
      ownerAffiliations: OWNER
      privacy: PUBLIC
      first: 100
      after: $cursor
      orderBy: {field: NAME, direction: ASC}
    ) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        nameWithOwner
        stargazerCount
        isPrivate
        owner { login }
      }
    }
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
            contributionLevel
            color
          }
        }
      }
    }
  }
  rateLimit { cost remaining resetAt }
}
""".strip()


REPOSITORY_PAGE_QUERY = """
query RepositoryPage($login: String!, $cursor: String!) {
  viewer { login }
  user(login: $login) {
    login
    repositories(
      ownerAffiliations: OWNER
      privacy: PUBLIC
      first: 100
      after: $cursor
      orderBy: {field: NAME, direction: ASC}
    ) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        nameWithOwner
        stargazerCount
        isPrivate
        owner { login }
      }
    }
  }
  rateLimit { cost remaining resetAt }
}
""".strip()


class GitHubStatsError(RuntimeError):
    """Base class for safe, user-facing retrieval failures."""


class AuthenticationError(GitHubStatsError):
    """Raised when credentials are missing, rejected, or belong to another user."""


class GraphQLResponseError(GitHubStatsError):
    """Raised when a GraphQL response cannot be safely consumed."""


class RateLimitError(GraphQLResponseError):
    """Raised when GitHub reports exhausted API capacity."""


class IncompleteDataError(GraphQLResponseError):
    """Raised when pagination or contribution coverage is incomplete."""


class TransportError(GitHubStatsError):
    """Raised when the API cannot be reached or decoded."""


@dataclass(frozen=True)
class ContributionWindow:
    """UTC query timestamps paired with expected Africa/Lagos dates."""

    start_date: date
    end_date: date
    from_datetime: datetime
    to_datetime: datetime


Transport = Callable[[str, Mapping[str, object]], Mapping[str, Any]]


def _utc_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("datetime values must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def contribution_window(
    now: datetime | None = None,
    *,
    days: int = SNAPSHOT_DAYS,
) -> ContributionWindow:
    """Build a complete local-date window ending today in Africa/Lagos."""

    if days <= 1:
        raise ValueError("contribution window must contain at least two days")
    zone = ZoneInfo(LOCAL_TIMEZONE)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    local_now = current.astimezone(zone)
    end_date = local_now.date()
    start_date = end_date - timedelta(days=days - 1)
    local_start = datetime.combine(start_date, time.min, tzinfo=zone)
    return ContributionWindow(
        start_date=start_date,
        end_date=end_date,
        from_datetime=local_start.astimezone(timezone.utc),
        to_datetime=current.astimezone(timezone.utc),
    )


def build_payload(
    login: str = USERNAME,
    *,
    end: datetime | None = None,
    days: int = SNAPSHOT_DAYS,
    cursor: str | None = None,
) -> dict[str, object]:
    """Build the initial profile request without performing network I/O."""

    if login != USERNAME:
        raise ValueError(f"this profile updater is pinned to {USERNAME!r}")
    if days <= 0:
        raise ValueError("days must be positive")
    end_value = end or datetime.now(timezone.utc)
    if end_value.tzinfo is None:
        raise ValueError("end must be timezone-aware")
    start_value = end_value - timedelta(days=days)
    return {
        "query": PROFILE_QUERY,
        "variables": {
            "login": login,
            "from": _utc_datetime(start_value),
            "to": _utc_datetime(end_value),
            "cursor": cursor,
        },
    }


def build_window_payload(
    window: ContributionWindow,
    *,
    login: str = USERNAME,
) -> dict[str, object]:
    if login != USERNAME:
        raise ValueError(f"this profile updater is pinned to {USERNAME!r}")
    return {
        "query": PROFILE_QUERY,
        "variables": {
            "login": login,
            "from": _utc_datetime(window.from_datetime),
            "to": _utc_datetime(window.to_datetime),
            "cursor": None,
        },
    }


def build_repository_page_payload(cursor: str) -> dict[str, object]:
    if not cursor:
        raise ValueError("repository cursor must not be empty")
    return {
        "query": REPOSITORY_PAGE_QUERY,
        "variables": {"login": USERNAME, "cursor": cursor},
    }


def _graphql_error_types(errors: Sequence[object]) -> tuple[str, ...]:
    types: set[str] = set()
    for error in errors:
        if isinstance(error, Mapping):
            error_type = error.get("type")
            extensions = error.get("extensions")
            if not error_type and isinstance(extensions, Mapping):
                error_type = extensions.get("type") or extensions.get("code")
            if isinstance(error_type, str) and error_type:
                types.add(error_type.upper())
    return tuple(sorted(types)) or ("UNKNOWN",)


def validate_response_envelope(response: Mapping[str, Any]) -> Mapping[str, Any]:
    """Reject GraphQL errors without echoing server text or credentials."""

    errors = response.get("errors")
    if errors:
        if not isinstance(errors, Sequence) or isinstance(errors, (str, bytes)):
            raise GraphQLResponseError("GitHub GraphQL returned malformed errors")
        error_types = _graphql_error_types(errors)
        if any(value in {"RATE_LIMITED", "RATE_LIMIT", "API_RATE_LIMIT_EXCEEDED"} for value in error_types):
            raise RateLimitError("GitHub GraphQL rate limit was exceeded")
        if any(value in {"UNAUTHORIZED", "FORBIDDEN", "UNAUTHENTICATED"} for value in error_types):
            raise AuthenticationError("GitHub rejected the supplied credentials")
        raise GraphQLResponseError(
            "GitHub GraphQL returned errors of type " + ", ".join(error_types)
        )
    data = response.get("data")
    if not isinstance(data, Mapping):
        raise GraphQLResponseError("GitHub GraphQL response has no data object")
    return data


def validate_viewer_login(response: Mapping[str, Any], expected: str = USERNAME) -> str:
    """Ensure the runtime token belongs to the intended profile owner."""

    data = validate_response_envelope(response)
    viewer = data.get("viewer")
    if not isinstance(viewer, Mapping):
        raise AuthenticationError("GitHub response did not identify the authenticated viewer")
    login = viewer.get("login")
    if not isinstance(login, str) or login.casefold() != expected.casefold():
        raise AuthenticationError(f"authenticated GitHub viewer is not {expected}")
    return expected


def resolve_token(
    environment: Mapping[str, str] | None = None,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    """Read a token from runtime state without displaying or persisting it."""

    env = environment if environment is not None else os.environ
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        token = env.get(name, "").strip()
        if token:
            return token
    try:
        result = runner(
            ["gh", "auth", "token"],
            check=False,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, OSError):
        raise AuthenticationError(
            "no runtime token was supplied and GitHub CLI is unavailable"
        ) from None
    token = result.stdout.strip() if result.returncode == 0 else ""
    if not token:
        raise AuthenticationError(
            "no runtime token was supplied and GitHub CLI is not authenticated"
        )
    return token


def execute_graphql(
    token: str,
    payload: Mapping[str, object],
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
    timeout: float = 30.0,
) -> Mapping[str, Any]:
    """POST one request while keeping credentials out of all raised errors."""

    if not token:
        raise AuthenticationError("GitHub token is empty")
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        GRAPHQL_ENDPOINT,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
            "User-Agent": "macanthonyeke-profile-updater",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with opener(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            raw = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise AuthenticationError("GitHub rejected the supplied credentials") from None
        if exc.code in {403, 429}:
            raise RateLimitError(
                f"GitHub API request was denied with HTTP {exc.code}"
            ) from None
        raise TransportError(f"GitHub API returned HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise TransportError("unable to reach the GitHub GraphQL API") from None
    except Exception:
        raise TransportError("GitHub GraphQL transport failed") from None
    if status != 200:
        raise TransportError(f"GitHub API returned HTTP {status}")
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise TransportError("GitHub API returned invalid JSON") from None
    if not isinstance(decoded, Mapping):
        raise TransportError("GitHub API returned a non-object JSON response")
    return decoded


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GraphQLResponseError(f"GitHub response is missing {label}")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GraphQLResponseError(f"GitHub response has invalid {label}")
    return value


def _user_data(data: Mapping[str, Any]) -> Mapping[str, Any]:
    user = _mapping(data.get("user"), "user data")
    login = user.get("login")
    if not isinstance(login, str) or login.casefold() != USERNAME.casefold():
        raise GraphQLResponseError(f"GitHub response user is not {USERNAME}")
    return user


def _rate_limit(data: Mapping[str, Any]) -> dict[str, object]:
    rate = _mapping(data.get("rateLimit"), "rate-limit data")
    cost = _nonnegative_int(rate.get("cost"), "rate-limit cost")
    remaining = _nonnegative_int(rate.get("remaining"), "rate-limit remaining")
    reset_at = rate.get("resetAt")
    if not isinstance(reset_at, str) or not reset_at:
        raise GraphQLResponseError("GitHub response has invalid rate-limit reset time")
    return {"cost": cost, "remaining": remaining, "reset_at": reset_at}


def _repository_page(
    connection: Mapping[str, Any],
) -> tuple[int, list[Mapping[str, Any]], bool, str | None]:
    total_count = _nonnegative_int(connection.get("totalCount"), "repository count")
    nodes = connection.get("nodes")
    if not isinstance(nodes, list):
        raise IncompleteDataError("GitHub repository page has no node list")
    normalized_nodes: list[Mapping[str, Any]] = []
    for node in nodes:
        repository = _mapping(node, "repository node")
        name = repository.get("nameWithOwner")
        owner = _mapping(repository.get("owner"), "repository owner")
        if not isinstance(name, str) or not name:
            raise GraphQLResponseError("GitHub repository has no name")
        if owner.get("login") != USERNAME or repository.get("isPrivate") is not False:
            raise GraphQLResponseError(
                "GitHub returned a repository outside the requested public ownership scope"
            )
        _nonnegative_int(repository.get("stargazerCount"), "repository star count")
        normalized_nodes.append(repository)
    page_info = _mapping(connection.get("pageInfo"), "repository page information")
    has_next = page_info.get("hasNextPage")
    if not isinstance(has_next, bool):
        raise IncompleteDataError("GitHub repository pagination flag is invalid")
    cursor = page_info.get("endCursor")
    if has_next and (not isinstance(cursor, str) or not cursor):
        raise IncompleteDataError("GitHub repository pagination cursor is missing")
    if cursor is not None and not isinstance(cursor, str):
        raise IncompleteDataError("GitHub repository pagination cursor is invalid")
    return total_count, normalized_nodes, has_next, cursor


def normalize_contributions(
    calendar: Mapping[str, Any],
    window: ContributionWindow,
) -> tuple[dict[str, object], ...]:
    """Normalize and verify one contiguous local-date contribution calendar."""

    weeks = calendar.get("weeks")
    if not isinstance(weeks, list):
        raise IncompleteDataError("GitHub contribution calendar has no weeks")
    by_date: dict[date, dict[str, object]] = {}
    for week in weeks:
        week_data = _mapping(week, "contribution week")
        days = week_data.get("contributionDays")
        if not isinstance(days, list):
            raise IncompleteDataError("GitHub contribution week has no days")
        for raw_day in days:
            day = _mapping(raw_day, "contribution day")
            raw_date = day.get("date")
            if not isinstance(raw_date, str):
                raise GraphQLResponseError("GitHub contribution day has no date")
            try:
                parsed_date = date.fromisoformat(raw_date)
            except ValueError:
                raise GraphQLResponseError(
                    "GitHub contribution day has an invalid date"
                ) from None
            count = _nonnegative_int(
                day.get("contributionCount"), "daily contribution count"
            )
            if parsed_date in by_date:
                raise IncompleteDataError(
                    f"GitHub contribution calendar duplicates {parsed_date.isoformat()}"
                )
            if window.start_date <= parsed_date <= window.end_date:
                level = day.get("contributionLevel")
                color = day.get("color")
                if not isinstance(level, str) or not isinstance(color, str):
                    raise GraphQLResponseError(
                        "GitHub contribution day is missing display metadata"
                    )
                by_date[parsed_date] = {
                    "date": parsed_date.isoformat(),
                    "count": count,
                    "level": level,
                    "color": color,
                }

    expected_dates = tuple(
        window.start_date + timedelta(days=offset)
        for offset in range((window.end_date - window.start_date).days + 1)
    )
    missing = [value for value in expected_dates if value not in by_date]
    if missing:
        raise IncompleteDataError(
            "GitHub contribution calendar coverage is incomplete; first missing date is "
            + missing[0].isoformat()
        )
    normalized = tuple(by_date[value] for value in expected_dates)
    reported_total = _nonnegative_int(
        calendar.get("totalContributions"), "total contributions"
    )
    calculated_total = sum(int(day["count"]) for day in normalized)
    if calculated_total != reported_total:
        raise IncompleteDataError(
            "GitHub contribution total does not match normalized daily counts"
        )
    return normalized


def calculate_current_streak(
    contributions: Sequence[Mapping[str, object]],
    *,
    today: date,
) -> int:
    """Calculate the current streak using the module-level documented semantics."""

    counts: dict[date, int] = {}
    for item in contributions:
        raw_date = item.get("date")
        raw_count = item.get("count")
        if not isinstance(raw_date, str):
            raise IncompleteDataError("normalized contribution date is invalid")
        try:
            parsed = date.fromisoformat(raw_date)
        except ValueError:
            raise IncompleteDataError("normalized contribution date is invalid") from None
        if parsed in counts:
            raise IncompleteDataError("normalized contribution dates are duplicated")
        counts[parsed] = _nonnegative_int(raw_count, "normalized contribution count")

    yesterday = today - timedelta(days=1)
    if today not in counts or yesterday not in counts:
        raise IncompleteDataError(
            "contribution coverage must include today and yesterday"
        )
    if counts[today] > 0:
        cursor = today
    elif counts[yesterday] > 0:
        cursor = yesterday
    else:
        return 0

    streak = 0
    while cursor in counts and counts[cursor] > 0:
        streak += 1
        cursor -= timedelta(days=1)
    if cursor not in counts:
        raise IncompleteDataError(
            "current streak reaches the beginning of available contribution data"
        )
    return streak


def fetch_github_snapshot(
    token: str,
    *,
    now: datetime | None = None,
    transport: Transport = execute_graphql,
) -> dict[str, object]:
    """Retrieve every page, validate it, and return one normalized snapshot."""

    window = contribution_window(now)
    generated_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    initial_response = transport(token, build_window_payload(window))
    validate_viewer_login(initial_response)
    data = validate_response_envelope(initial_response)
    user = _user_data(data)
    contributions_collection = _mapping(
        user.get("contributionsCollection"), "contributions collection"
    )
    calendar = _mapping(
        contributions_collection.get("contributionCalendar"),
        "contribution calendar",
    )
    contributions = normalize_contributions(calendar, window)
    current_streak = calculate_current_streak(
        contributions, today=window.end_date
    )

    repository_connection = _mapping(
        user.get("repositories"), "repository connection"
    )
    total_count, repositories, has_next, cursor = _repository_page(
        repository_connection
    )
    seen_names = {str(repository["nameWithOwner"]) for repository in repositories}
    seen_cursors: set[str] = set()
    rate_limits = [_rate_limit(data)]

    while has_next:
        if cursor is None or cursor in seen_cursors:
            raise IncompleteDataError("GitHub repository pagination did not advance")
        seen_cursors.add(cursor)
        page_response = transport(token, build_repository_page_payload(cursor))
        validate_viewer_login(page_response)
        page_data = validate_response_envelope(page_response)
        page_user = _user_data(page_data)
        page_connection = _mapping(
            page_user.get("repositories"), "repository connection"
        )
        page_total, page_nodes, has_next, cursor = _repository_page(page_connection)
        if page_total != total_count:
            raise IncompleteDataError(
                "GitHub repository count changed during pagination"
            )
        for repository in page_nodes:
            name = str(repository["nameWithOwner"])
            if name in seen_names:
                raise IncompleteDataError(
                    "GitHub repository pagination returned a duplicate repository"
                )
            seen_names.add(name)
            repositories.append(repository)
        rate_limits.append(_rate_limit(page_data))

    if len(repositories) != total_count:
        raise IncompleteDataError(
            f"GitHub repository pagination returned {len(repositories)} of {total_count} repositories"
        )
    total_stars = sum(
        _nonnegative_int(repository.get("stargazerCount"), "repository star count")
        for repository in repositories
    )
    total_contributions = sum(int(day["count"]) for day in contributions)

    return {
        "version": 1,
        "username": USERNAME,
        "timezone": LOCAL_TIMEZONE,
        "generated_at": _utc_datetime(generated_at),
        "period": {
            "from": window.start_date.isoformat(),
            "to": window.end_date.isoformat(),
            "days": len(contributions),
        },
        "statistics": {
            "total_contributions": total_contributions,
            "current_streak": current_streak,
            "public_repositories": total_count,
            "total_stars": total_stars,
        },
        "contributions": list(contributions),
        "api": {
            "requests": len(rate_limits),
            "total_cost": sum(int(rate["cost"]) for rate in rate_limits),
            "remaining": min(int(rate["remaining"]) for rate in rate_limits),
            "reset_at": rate_limits[-1]["reset_at"],
        },
    }


def write_snapshot(snapshot: Mapping[str, object], output_path: Path) -> Path:
    """Atomically replace the normalized snapshot only after full validation."""

    serialized = json.dumps(
        snapshot,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            delete=False,
        ) as temporary:
            temporary.write(serialized)
            temporary_name = temporary.name
        os.replace(temporary_name, output_path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return output_path


def update_snapshot(
    output_path: Path,
    token: str,
    *,
    now: datetime | None = None,
    transport: Transport = execute_graphql,
) -> dict[str, object]:
    """Fetch first, then atomically write; failures leave existing data untouched."""

    snapshot = fetch_github_snapshot(token, now=now, transport=transport)
    write_snapshot(snapshot, output_path)
    return snapshot


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="path for the validated normalized snapshot",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        token = resolve_token()
        snapshot = update_snapshot(args.output, token)
    except GitHubStatsError as exc:
        print(f"GitHub statistics update failed: {exc}", file=sys.stderr)
        return 1
    statistics = _mapping(snapshot.get("statistics"), "normalized statistics")
    print(f"wrote validated GitHub snapshot: {args.output}")
    print(
        "contributions={total_contributions} streak={current_streak} "
        "public_repositories={public_repositories} stars={total_stars}".format(
            **statistics
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
