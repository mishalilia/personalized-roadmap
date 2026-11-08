import base64
import json
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from roadmap import Roadmap
from roadmap.accounts import AccountStore
from roadmap.api import Edition, RateLimiter, create_app
from roadmap.google import GoogleSignIn

SITE = "https://curriculum.example"
CLIENT_ID = "client-123.apps.googleusercontent.com"
PAGE = f"{SITE}/docs/basics/terminal"


def id_token(**claims: object) -> str:
    """An ID token as Google's token endpoint returns it; the signature is not checked, so any will do."""
    body = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "google-user-1",
        "email": "learner@gmail.com",
        "email_verified": True,
        "exp": int(time.time()) + 600,
    } | claims

    def part(value: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")

    return f"{part({'alg': 'RS256'})}.{part(body)}.signature"


class FakeGoogle:
    """Google's token endpoint: answers with the given ID token claims and records what it was sent."""

    def __init__(self, **claims: object) -> None:
        self.claims = claims
        self.sent: list[dict[str, list[str]]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.sent.append(parse_qs(request.content.decode()))
        return httpx.Response(200, json={"id_token": id_token(**self.claims)})


def site(curriculum, questions, google: FakeGoogle) -> tuple[TestClient, AccountStore]:
    accounts = AccountStore(Path(":memory:"))
    sign_in = GoogleSignIn(
        CLIENT_ID,
        "secret",  # nosec B106: a test secret
        "https://api.example/auth/google/callback",
        http=httpx.Client(transport=httpx.MockTransport(google.handler)),
    )
    app = create_app(
        [Edition(Roadmap(curriculum, questions, llm=None), {})],
        [SITE],
        RateLimiter(100, window=3600),
        accounts=accounts,
        google=sign_in,
    )
    return (
        TestClient(app, base_url="https://testserver", follow_redirects=False),
        accounts,
    )


def start(client: TestClient, draft_id: str | None = None) -> dict[str, str]:
    """Starts a sign-in and returns the query of Google's address the learner is sent to."""
    params = {"return_to": PAGE} | ({"draft_id": draft_id} if draft_id else {})
    response = client.get("/auth/google", params=params)
    assert response.status_code == 303
    location = urlparse(response.headers["location"])
    assert location.netloc == "accounts.google.com"
    return {key: values[0] for key, values in parse_qs(location.query).items()}


def test_a_learner_signs_in_with_google_and_keeps_the_path_they_planned(
    curriculum, questions
):
    google = FakeGoogle()
    client, _ = site(curriculum, questions, google)
    planned = client.post(
        "/path", json={"answers": {"goal": "Computer vision"}, "level": None}
    ).json()

    query = start(client, planned["draft_id"])
    back = client.get(
        "/auth/google/callback", params={"state": query["state"], "code": "one-time"}
    )

    assert query["client_id"] == CLIENT_ID and query["code_challenge_method"] == "S256"
    assert back.status_code == 303 and back.headers["location"] == PAGE
    session = client.get("/auth/session").json()
    assert session["account"]["email"] == "learner@gmail.com"
    assert not session["account"]["has_password"]  # made with Google
    assert session["path"]["id"] == planned["path"]["id"]
    # The code went to Google with the secret and the PKCE verifier.
    sent = google.sent[0]
    assert sent["code"] == ["one-time"] and sent["client_secret"] == ["secret"]
    assert sent["code_verifier"][0]


def test_google_signs_into_the_account_with_the_same_address(curriculum, questions):
    client, accounts = site(curriculum, questions, FakeGoogle())
    accounts.sign_up("learner@gmail.com", "correct horse battery")  # nosec B106

    query = start(client)
    client.get("/auth/google/callback", params={"state": query["state"], "code": "c"})

    account = client.get("/auth/session").json()["account"]
    assert account["email"] == "learner@gmail.com"
    assert account["has_password"]  # the same account, which keeps its password


@pytest.mark.parametrize(
    "claims",
    [
        {"aud": "someone-else"},
        {"iss": "https://evil.example"},
        {"email_verified": False},
        {"exp": 1},
    ],
)
def test_a_token_that_is_not_for_this_site_signs_nobody_in(
    curriculum, questions, claims
):
    client, _ = site(curriculum, questions, FakeGoogle(**claims))

    query = start(client)
    back = client.get(
        "/auth/google/callback", params={"state": query["state"], "code": "c"}
    )

    assert back.headers["location"] == f"{PAGE}#sign-in-error=google"
    assert client.get("/auth/session").json()["account"] is None


def test_a_callback_needs_the_state_of_this_browser_and_works_once(
    curriculum, questions
):
    client, _ = site(curriculum, questions, FakeGoogle())
    query = start(client)
    other_browser = TestClient(client.app, base_url="https://testserver")

    elsewhere = other_browser.get(
        "/auth/google/callback", params={"state": query["state"], "code": "c"}
    )
    first = client.get(
        "/auth/google/callback", params={"state": query["state"], "code": "c"}
    )
    again = client.get(
        "/auth/google/callback", params={"state": query["state"], "code": "c"}
    )

    assert elsewhere.status_code == 400
    assert first.status_code == 303
    assert again.status_code == 400


def test_cancelling_at_google_returns_to_the_page(curriculum, questions):
    client, _ = site(curriculum, questions, FakeGoogle())
    query = start(client)

    back = client.get(
        "/auth/google/callback",
        params={"state": query["state"], "error": "access_denied"},
    )

    assert back.headers["location"] == f"{PAGE}#sign-in-error=cancelled"


def test_sign_in_returns_only_to_the_course_site(curriculum, questions):
    client, _ = site(curriculum, questions, FakeGoogle())

    response = client.get("/auth/google", params={"return_to": "https://evil.example/"})

    assert response.status_code == 422


def test_an_account_made_with_google_is_deleted_by_typing_its_address(
    curriculum, questions
):
    client, _ = site(curriculum, questions, FakeGoogle())
    query = start(client)
    client.get("/auth/google/callback", params={"state": query["state"], "code": "c"})

    wrong = client.post("/auth/delete", json={"confirmation": "someone@gmail.com"})
    deleted = client.post("/auth/delete", json={"confirmation": "Learner@gmail.com"})

    assert wrong.status_code == 401
    assert deleted.status_code == 200


def test_without_a_client_google_is_not_offered(curriculum, questions):
    app = create_app(
        [Edition(Roadmap(curriculum, questions, llm=None), {})],
        [SITE],
        RateLimiter(100, window=3600),
    )
    client = TestClient(app)

    assert client.get("/auth/providers").json() == {"google": False}
    assert client.get("/auth/google", params={"return_to": PAGE}).status_code == 404
