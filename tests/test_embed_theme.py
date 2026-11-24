"""The panel's look on a school's site: the school's designers change it, every visitor gets it, and no one
else may change it."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from test_embed import COURSE, OTHER, PASSWORD, SCHOOL, embedded

from roadmap import Roadmap
from roadmap.accounts import AccountStore
from roadmap.api import EmbedSite, EmbedThemes, Edition, RateLimiter, create_app

DESIGNER = "brand@school.example"
SITES = {
    SCHOOL: EmbedSite.model_validate(
        {
            "versions": [{"name": "current", "label": "Current", "docs": []}],
            "content": "#lesson",
            "theme": {"accent": "#2255aa"},
            "designers": [DESIGNER.upper()],
        }
    )
}
LIGHT = {
    "mode": "light",
    "accent": "#c2410c",
    "font": "serif",
    "corners": "round",
    "logo": None,
}


def site(curriculum, questions, themes: Path | None = None) -> TestClient:
    app = create_app(
        [Edition(Roadmap(curriculum, questions, llm=None), {})],
        [COURSE, SCHOOL],
        RateLimiter(100, window=3600),
        accounts=AccountStore(Path(":memory:")),
        embed_sites=SITES,
        embed_themes=EmbedThemes(themes),
    )
    return TestClient(app, base_url="https://testserver")


def token_of(client: TestClient, email: str) -> dict[str, str]:
    token = client.post(
        "/auth/sign-up", json={"email": email, "password": PASSWORD}, headers=embedded()
    ).json()["token"]
    return {**embedded(), "Authorization": f"Bearer {token}"}


def test_the_site_starts_with_the_engineers_look_and_never_shows_its_designers(
    curriculum, questions
):
    client = site(curriculum, questions)

    found = client.get("/embed/site", headers={"Origin": SCHOOL}).json()

    assert found["theme"]["accent"] == "#2255aa"
    assert found["theme"]["mode"] == "dark"
    assert "designers" not in found


def test_a_designer_saves_the_look_and_every_visitor_gets_it(
    curriculum, questions, tmp_path
):
    file = tmp_path / "themes" / "embed-themes.json"
    client = site(curriculum, questions, file)
    designer = token_of(client, DESIGNER)

    assert client.get("/embed/designer", headers=designer).json() == {"designer": True}
    saved = client.post("/embed/theme", json=LIGHT, headers=designer)

    assert saved.status_code == 200
    assert (
        client.get("/embed/site", headers={"Origin": SCHOOL}).json()["theme"] == LIGHT
    )
    # It outlasts a restart of the API.
    assert json.loads(file.read_text(encoding="utf-8"))[SCHOOL] == LIGHT
    again = site(curriculum, questions, file)
    assert again.get("/embed/site", headers={"Origin": SCHOOL}).json()["theme"] == LIGHT


def test_no_one_else_may_change_the_look(curriculum, questions):
    client = site(curriculum, questions)
    learner = token_of(client, "learner@example.com")

    assert client.get("/embed/designer", headers=learner).json() == {"designer": False}
    assert client.post("/embed/theme", json=LIGHT, headers=learner).status_code == 403
    # A visitor who is not signed in at all.
    visitor = TestClient(client.app, base_url="https://testserver")
    assert visitor.get("/embed/designer", headers=embedded()).json() == {
        "designer": False
    }
    assert (
        visitor.post("/embed/theme", json=LIGHT, headers=embedded()).status_code == 401
    )
    assert (
        client.get("/embed/site", headers={"Origin": SCHOOL}).json()["theme"]["mode"]
        == "dark"
    )


def test_another_site_cannot_change_the_look(curriculum, questions):
    client = site(curriculum, questions)
    designer = token_of(client, DESIGNER)

    refused = client.post(
        "/embed/theme", json=LIGHT, headers={**designer, "Origin": OTHER}
    )

    assert refused.status_code in (403, 404)


def test_a_look_carries_no_css_of_its_own(curriculum, questions):
    client = site(curriculum, questions)
    designer = token_of(client, DESIGNER)

    for bad in (
        {"accent": "red; background: url(x)"},
        {"accent": "#12345"},
        {"font": "Comic Sans"},
        {"logo": "javascript:alert(1)"},
        {"logo": "https://x.example/a.png) ; color: red"},
    ):
        assert (
            client.post("/embed/theme", json=bad, headers=designer).status_code == 422
        ), bad


def test_each_site_keeps_its_own_look(curriculum, questions, tmp_path):
    # A second school with its own designer: neither can touch the other's look.
    second = "https://academy.example"
    sites = {
        **SITES,
        second: EmbedSite.model_validate(
            {
                "versions": [{"name": "current", "label": "Current", "docs": []}],
                "content": "#lesson",
                "designers": ["design@academy.example"],
            }
        ),
    }
    app = create_app(
        [Edition(Roadmap(curriculum, questions, llm=None), {})],
        [COURSE, SCHOOL, second],
        RateLimiter(100, window=3600),
        accounts=AccountStore(Path(":memory:")),
        embed_sites=sites,
        embed_themes=EmbedThemes(tmp_path / "embed-themes.json"),
    )
    client = TestClient(app, base_url="https://testserver")
    school = token_of(client, DESIGNER)
    academy = {**token_of(client, "design@academy.example"), "Origin": second}
    orange = {**LIGHT, "mode": "dark", "accent": "#ff8800", "font": "system"}

    assert client.post("/embed/theme", json=LIGHT, headers=school).status_code == 200
    assert client.post("/embed/theme", json=orange, headers=academy).status_code == 200
    # The school's designer on the academy's site is just a learner there.
    assert (
        client.post(
            "/embed/theme", json=LIGHT, headers={**school, "Origin": second}
        ).status_code
        == 403
    )

    assert (
        client.get("/embed/site", headers={"Origin": SCHOOL}).json()["theme"] == LIGHT
    )
    assert (
        client.get("/embed/site", headers={"Origin": second}).json()["theme"] == orange
    )
