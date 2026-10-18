import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import github_graphql


NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


def calendar_fixture(counts=None, *, now=NOW, empty_weeks=False):
    window = github_graphql.contribution_window(now)
    counts = counts or {}
    days = []
    cursor = window.start_date
    while cursor <= window.end_date:
        count = counts.get(cursor, 0)
        days.append(
            {
                "date": cursor.isoformat(),
                "contributionCount": count,
                "contributionLevel": "NONE" if count == 0 else "FIRST_QUARTILE",
                "color": "#ebedf0" if count == 0 else "#9be9a8",
            }
        )
        cursor += timedelta(days=1)
    return {
        "totalContributions": sum(counts.values()),
        "weeks": [] if empty_weeks else [{"contributionDays": days}],
    }


def repository(name, stars):
    return {
        "nameWithOwner": f"macanthonyeke/{name}",
        "stargazerCount": stars,
        "isPrivate": False,
        "owner": {"login": "macanthonyeke"},
    }


def repository_connection(nodes, *, total=None, has_next=False, cursor=None):
    return {
        "totalCount": len(nodes) if total is None else total,
        "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
        "nodes": nodes,
    }


def initial_response(
    calendar,
    repositories,
    *,
    viewer="macanthonyeke",
    total=None,
    has_next=False,
    cursor=None,
    remaining=4990,
):
    return {
        "data": {
            "viewer": {"login": viewer},
            "user": {
                "login": "macanthonyeke",
                "repositories": repository_connection(
                    repositories,
                    total=total,
                    has_next=has_next,
                    cursor=cursor,
                ),
                "contributionsCollection": {
                    "contributionCalendar": calendar,
                },
            },
            "rateLimit": {
                "cost": 1,
                "remaining": remaining,
                "resetAt": "2026-10-18T14:00:00Z",
            },
        }
    }


def page_response(repositories, *, total, has_next=False, cursor=None, remaining=4989):
    return {
        "data": {
            "viewer": {"login": "macanthonyeke"},
            "user": {
                "login": "macanthonyeke",
                "repositories": repository_connection(
                    repositories,
                    total=total,
                    has_next=has_next,
                    cursor=cursor,
                ),
            },
            "rateLimit": {
                "cost": 1,
                "remaining": remaining,
                "resetAt": "2026-10-18T14:00:00Z",
            },
        }
    }


class SequenceTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.payloads = []

    def __call__(self, token, payload):
        self.payloads.append(payload)
        if not self.responses:
            raise AssertionError("unexpected GraphQL request")
        return self.responses.pop(0)


class GraphQLContractTests(unittest.TestCase):
    def test_payload_is_built_without_network_access(self):
        payload = github_graphql.build_payload(end=NOW, days=7)
        self.assertEqual(payload["variables"]["login"], "macanthonyeke")
        self.assertEqual(payload["variables"]["from"], "2026-10-11T12:00:00Z")
        self.assertEqual(payload["variables"]["to"], "2026-10-18T12:00:00Z")
        self.assertIsNone(payload["variables"]["cursor"])
        self.assertIn("contributionCalendar", payload["query"])
        self.assertIn("privacy: PUBLIC", payload["query"])

    def test_successful_authenticated_response_is_normalized(self):
        today = github_graphql.contribution_window(NOW).end_date
        counts = {today: 3, today - timedelta(days=1): 2}
        transport = SequenceTransport(
            initial_response(
                calendar_fixture(counts),
                [repository("one", 4), repository("two", 7)],
            )
        )
        snapshot = github_graphql.fetch_github_snapshot(
            "secret-token", now=NOW, transport=transport
        )
        self.assertEqual(
            snapshot["statistics"],
            {
                "total_contributions": 5,
                "current_streak": 2,
                "public_repositories": 2,
                "total_stars": 11,
            },
        )
        self.assertEqual(len(snapshot["contributions"]), 365)
        self.assertNotIn("secret-token", json.dumps(snapshot))

    def test_repository_stars_are_paginated(self):
        transport = SequenceTransport(
            initial_response(
                calendar_fixture(),
                [repository("one", 2)],
                total=3,
                has_next=True,
                cursor="page-2",
            ),
            page_response(
                [repository("two", 5), repository("three", 11)],
                total=3,
            ),
        )
        snapshot = github_graphql.fetch_github_snapshot(
            "secret-token", now=NOW, transport=transport
        )
        self.assertEqual(snapshot["statistics"]["public_repositories"], 3)
        self.assertEqual(snapshot["statistics"]["total_stars"], 18)
        self.assertEqual(snapshot["api"]["requests"], 2)
        self.assertEqual(
            transport.payloads[1]["variables"]["cursor"], "page-2"
        )

    def test_empty_contribution_calendar_has_zero_streak(self):
        transport = SequenceTransport(initial_response(calendar_fixture(), []))
        snapshot = github_graphql.fetch_github_snapshot(
            "secret-token", now=NOW, transport=transport
        )
        self.assertEqual(snapshot["statistics"]["total_contributions"], 0)
        self.assertEqual(snapshot["statistics"]["current_streak"], 0)

    def test_streak_continues_from_today(self):
        today = date(2026, 10, 18)
        contributions = [
            {"date": "2026-10-15", "count": 0},
            {"date": "2026-10-16", "count": 1},
            {"date": "2026-10-17", "count": 2},
            {"date": "2026-10-18", "count": 1},
        ]
        self.assertEqual(
            github_graphql.calculate_current_streak(contributions, today=today), 3
        )

    def test_streak_continues_from_yesterday_when_today_is_empty(self):
        today = date(2026, 10, 18)
        contributions = [
            {"date": "2026-10-14", "count": 0},
            {"date": "2026-10-15", "count": 1},
            {"date": "2026-10-16", "count": 1},
            {"date": "2026-10-17", "count": 3},
            {"date": "2026-10-18", "count": 0},
        ]
        self.assertEqual(
            github_graphql.calculate_current_streak(contributions, today=today), 3
        )

    def test_broken_streak_is_zero(self):
        today = date(2026, 10, 18)
        contributions = [
            {"date": "2026-10-16", "count": 8},
            {"date": "2026-10-17", "count": 0},
            {"date": "2026-10-18", "count": 0},
        ]
        self.assertEqual(
            github_graphql.calculate_current_streak(contributions, today=today), 0
        )

    def test_year_boundary_uses_africa_lagos_date(self):
        now = datetime(2026, 12, 31, 23, 30, tzinfo=timezone.utc)
        window = github_graphql.contribution_window(now)
        self.assertEqual(window.end_date, date(2027, 1, 1))
        self.assertEqual(window.start_date, date(2026, 1, 2))
        self.assertEqual(
            github_graphql._utc_datetime(window.from_datetime),
            "2026-01-01T23:00:00Z",
        )

    def test_graphql_and_rate_limit_errors_are_rejected(self):
        with self.assertRaises(github_graphql.GraphQLResponseError):
            github_graphql.validate_response_envelope(
                {"errors": [{"type": "SOMETHING_FAILED", "message": "unsafe"}]}
            )
        with self.assertRaises(github_graphql.RateLimitError):
            github_graphql.validate_response_envelope(
                {"errors": [{"type": "RATE_LIMITED"}]}
            )

    def test_incomplete_calendar_is_rejected(self):
        transport = SequenceTransport(
            initial_response(calendar_fixture(empty_weeks=True), [])
        )
        with self.assertRaises(github_graphql.IncompleteDataError):
            github_graphql.fetch_github_snapshot(
                "secret-token", now=NOW, transport=transport
            )

    def test_incomplete_pagination_is_rejected(self):
        transport = SequenceTransport(
            initial_response(
                calendar_fixture(), [repository("one", 1)], total=2
            )
        )
        with self.assertRaises(github_graphql.IncompleteDataError):
            github_graphql.fetch_github_snapshot(
                "secret-token", now=NOW, transport=transport
            )

    def test_token_is_redacted_from_transport_failures(self):
        secret = "ghp_do-not-display-this-token"

        def failing_opener(*args, **kwargs):
            raise RuntimeError(f"transport leaked {secret}")

        with self.assertRaises(github_graphql.TransportError) as raised:
            github_graphql.execute_graphql(
                secret,
                github_graphql.build_payload(end=NOW, days=7),
                opener=failing_opener,
            )
        self.assertNotIn(secret, str(raised.exception))

    def test_incorrect_authenticated_viewer_is_rejected(self):
        response = initial_response(calendar_fixture(), [], viewer="someone-else")
        with self.assertRaises(github_graphql.AuthenticationError):
            github_graphql.validate_viewer_login(response)

    def test_normalization_is_deterministic(self):
        window = github_graphql.contribution_window(NOW)
        calendar = calendar_fixture({window.end_date: 1})
        first = github_graphql.normalize_contributions(calendar, window)
        second = github_graphql.normalize_contributions(calendar, window)
        self.assertEqual(first, second)
        self.assertEqual(first[0]["date"], window.start_date.isoformat())
        self.assertEqual(first[-1]["date"], window.end_date.isoformat())

    def test_failed_update_does_not_replace_existing_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "stats.json"
            output.write_text("preserve-me\n", encoding="utf-8")

            def failing_transport(token, payload):
                raise github_graphql.TransportError("safe failure")

            with self.assertRaises(github_graphql.TransportError):
                github_graphql.update_snapshot(
                    output,
                    "secret-token",
                    now=NOW,
                    transport=failing_transport,
                )
            self.assertEqual(output.read_text(encoding="utf-8"), "preserve-me\n")

    def test_environment_token_precedes_cli_lookup(self):
        def unexpected_runner(*args, **kwargs):
            raise AssertionError("GitHub CLI should not run")

        self.assertEqual(
            github_graphql.resolve_token(
                {"GITHUB_TOKEN": " runtime-secret "}, runner=unexpected_runner
            ),
            "runtime-secret",
        )


if __name__ == "__main__":
    unittest.main()
