"""The panel embedded in another site with a script tag (embed/): a session by token instead of the cookie,
the site's pages, Google sign-in in a window of its own, and the script itself."""

import json
import re
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import httpx
from fastapi.testclient import TestClient
from test_google import CLIENT_ID, FakeGoogle

from roadmap import Roadmap
from roadmap.accounts import AccountStore
from roadmap.api import EMBED_HEADER, EmbedSite, Edition, RateLimiter, create_app
from roadmap.google import GoogleSignIn

COURSE = "https://curriculum.example"
SCHOOL = "https://school.example"
OTHER = "https://evil.example"
API = "https://api.example"
PASSWORD = "correct horse battery"  # nosec B105  # pragma: allowlist secret
SITES = {
    SCHOOL: EmbedSite.model_validate(
        {
            "versions": [
                {
                    "name": "current",
                    "label": "Current",
                    "docs": [{"id": "basics/terminal", "path": "/lessons/terminal"}],
                }
            ],
            "content": "#lesson",
        }
    )
}


def site(
    curriculum,
    questions,
    tmp_path: Path | None = None,
    google: FakeGoogle | None = None,
):
    accounts = AccountStore(Path(":memory:"))
    sign_in = (
        GoogleSignIn(
            CLIENT_ID,
            "secret",  # nosec B106: a test secret
            f"{API}/auth/google/callback",
            http=httpx.Client(transport=httpx.MockTransport(google.handler)),
        )
        if google
        else None
    )
    app = create_app(
        [Edition(Roadmap(curriculum, questions, llm=None), {})],
        [COURSE, SCHOOL],
        RateLimiter(100, window=3600),
        accounts=accounts,
        google=sign_in,
        embed_sites=SITES,
        embed_dir=tmp_path,
        public_url=API,
    )
    return (
        TestClient(app, base_url="https://testserver", follow_redirects=False),
        accounts,
    )


def embedded() -> dict[str, str]:
    return {"Origin": SCHOOL, EMBED_HEADER: "1"}


def test_the_embedded_panel_gets_a_token_and_signs_in_with_it(curriculum, questions):
    client, _ = site(curriculum, questions)
    signed_up = client.post(
        "/auth/sign-up",
        json={"email": "learner@example.com", "password": PASSWORD},
        headers=embedded(),
    ).json()
    token = signed_up["token"]

    # Another browser without the cookie, as a site whose browser blocks the API's cookie.
    other = TestClient(client.app, base_url="https://testserver")
    session = other.get(
        "/auth/session", headers={"Authorization": f"Bearer {token}", "Origin": SCHOOL}
    ).json()

    assert session["account"]["email"] == "learner@example.com"
    assert "token" not in session  # handed out only when signing in


def test_the_course_site_never_sees_the_token(curriculum, questions):
    client, _ = site(curriculum, questions)

    signed_up = client.post(
        "/auth/sign-up", json={"email": "learner@example.com", "password": PASSWORD}
    ).json()

    assert "token" not in signed_up
    assert (
        client.get("/auth/session").json()["account"]["email"] == "learner@example.com"
    )


def test_signing_out_ends_the_token(curriculum, questions):
    client, accounts = site(curriculum, questions)
    token = client.post(
        "/auth/sign-up",
        json={"email": "learner@example.com", "password": PASSWORD},
        headers=embedded(),
    ).json()["token"]
    bearer = {"Authorization": f"Bearer {token}", "Origin": SCHOOL}
    other = TestClient(client.app, base_url="https://testserver")

    other.post("/auth/sign-out", json={}, headers=bearer)

    assert accounts.account_for(token) is None
    assert other.get("/auth/session", headers=bearer).json()["account"] is None


def test_requests_carry_the_token_through_cors(curriculum, questions):
    client, _ = site(curriculum, questions)

    preflight = client.options(
        "/me/path/confirm",
        headers={
            "Origin": SCHOOL,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": f"authorization,content-type,{EMBED_HEADER.lower()}",
        },
    )

    assert preflight.status_code == 200
    allowed = preflight.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed and EMBED_HEADER.lower() in allowed


def test_a_site_not_allowed_cannot_change_anything(curriculum, questions):
    client, _ = site(curriculum, questions)

    response = client.post(
        "/auth/sign-up",
        json={"email": "learner@example.com", "password": PASSWORD},
        headers={"Origin": OTHER, EMBED_HEADER: "1"},
    )

    assert response.status_code == 403


def test_the_school_gets_its_pages(curriculum, questions):
    client, _ = site(curriculum, questions)

    pages = client.get("/embed/site", headers={"Origin": SCHOOL})
    unknown = client.get("/embed/site", headers={"Origin": OTHER})

    assert pages.status_code == 200
    assert pages.json()["versions"][0]["docs"] == [
        {"id": "basics/terminal", "path": "/lessons/terminal"}
    ]
    assert pages.json()["content"] == "#lesson"
    assert unknown.status_code == 404


def test_the_script_is_served_when_built(curriculum, questions, tmp_path):
    client, _ = site(curriculum, questions, tmp_path)
    missing = client.get("/embed/dotpath.js")
    (tmp_path / "dotpath.js").write_text("console.log('panel');", encoding="utf-8")

    served = client.get("/embed/dotpath.js")

    assert missing.status_code == 404
    assert served.status_code == 200
    assert served.headers["content-type"].startswith("text/javascript")
    assert served.text == "console.log('panel');"


def signed_in_page(origin: str) -> str:
    return f"{API}/embed/signed-in?origin={quote(origin, safe='')}"


def message_of(page: str) -> tuple[dict, str]:
    sent = re.search(r"const message = (.*);", page)
    target = re.search(r"postMessage\(message, (.*)\);", page)
    assert sent and target
    return json.loads(sent.group(1)), json.loads(target.group(1))


def test_google_sign_in_hands_the_session_to_the_embedding_site_only(
    curriculum, questions
):
    google = FakeGoogle()
    client, accounts = site(curriculum, questions, google=google)

    start = client.get("/auth/google", params={"return_to": signed_in_page(SCHOOL)})
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    back = client.get(
        "/auth/google/callback", params={"state": state, "code": "one-time"}
    )
    assert back.headers["location"] == signed_in_page(SCHOOL)
    page = client.get(
        urlparse(back.headers["location"]).path
        + "?"
        + urlparse(back.headers["location"]).query
    )

    message, target = message_of(page.text)
    assert page.status_code == 200 and page.headers["cache-control"] == "no-store"
    assert target == SCHOOL
    signed_in = accounts.account_for(message["token"])
    assert signed_in is not None and signed_in.email == "learner@gmail.com"


def test_google_sign_in_cannot_return_to_a_site_not_allowed(curriculum, questions):
    client, _ = site(curriculum, questions, google=FakeGoogle())

    start = client.get("/auth/google", params={"return_to": signed_in_page(OTHER)})
    page = client.get("/embed/signed-in", params={"origin": OTHER})

    assert start.status_code == 422
    assert page.status_code == 400


def test_without_a_session_the_page_hands_over_no_token(curriculum, questions):
    client, _ = site(curriculum, questions, google=FakeGoogle())

    page = client.get("/embed/signed-in", params={"origin": SCHOOL})

    message, target = message_of(page.text)
    assert "token" not in message and target == SCHOOL
