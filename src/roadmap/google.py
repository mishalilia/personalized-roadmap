"""Sign-in with Google: the OAuth 2.0 authorization code flow with PKCE, run by the API, not the browser.

The learner's browser goes to Google and comes back to the API with a one-time code; the API trades the code,
with its client secret, for an ID token straight from Google's token endpoint. A token received that way, over
TLS from Google itself, need not have its signature checked (OpenID Connect Core 1.0, 3.1.3.7); its issuer,
audience, expiry and verified email are checked here. No Google script runs on the site.

Set up a client in Google Cloud Console (APIs & Services → Credentials → OAuth client ID, type "Web
application"), with `<API address>/auth/google/callback` as an authorized redirect URI, and put its id and secret
in GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = (
    "https://oauth2.googleapis.com/token"  # nosec B105: an address, not a password
)
ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
FLOW_SECONDS = 600  # how long a learner has to finish signing in at Google


class GoogleError(Exception):
    """Google did not confirm who the learner is."""


@dataclass(frozen=True)
class Identity:
    subject: str  # Google's id for the user
    email: str


@dataclass(frozen=True)
class Flow:
    """One sign-in in progress: what to send to Google, and where the learner goes afterwards."""

    verifier: str
    return_to: str
    draft_id: str | None
    started: float


class GoogleSignIn:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        http: httpx.Client | None = None,
        clock=time.time,  # type: ignore[no-untyped-def]
    ) -> None:
        self.client_id = client_id
        self._secret = client_secret
        self.redirect_uri = redirect_uri
        self._http = http or httpx.Client(timeout=10)
        self._clock = clock
        # Sign-ins in progress, by state. In memory: one API worker, and a restart only asks to start again.
        self._flows: dict[str, Flow] = {}
        self._lock = threading.Lock()

    def start(self, return_to: str, draft_id: str | None) -> tuple[str, str]:
        """Google's sign-in address for a new flow, and the flow's state, which the browser keeps in a cookie
        so that only the browser that started the flow can finish it."""
        state = secrets.token_urlsafe(24)
        verifier = secrets.token_urlsafe(48)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        now = self._clock()
        with self._lock:
            self._flows = {
                key: flow
                for key, flow in self._flows.items()
                if now - flow.started < FLOW_SECONDS
            }
            self._flows[state] = Flow(verifier, return_to, draft_id, now)
        query = urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "scope": "openid email",
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "prompt": "select_account",
            }
        )
        return f"{AUTHORIZE_URL}?{query}", state

    def flow(self, state: str) -> Flow | None:
        """The flow a callback finishes, once; None if unknown or too old."""
        with self._lock:
            flow = self._flows.pop(state, None)
        if flow is None or self._clock() - flow.started >= FLOW_SECONDS:
            return None
        return flow

    def identity(self, code: str, flow: Flow) -> Identity:
        """Trades the code for an ID token and returns who signed in."""
        try:
            response = self._http.post(
                TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self._secret,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": flow.verifier,
                },
            )
        except httpx.HTTPError as error:
            raise GoogleError("Google could not be reached") from error
        if response.status_code != 200:
            raise GoogleError(f"Google refused the code ({response.status_code})")
        token = response.json().get("id_token")
        if not isinstance(token, str):
            raise GoogleError("Google sent no ID token")
        claims = _claims(token)
        if claims.get("iss") not in ISSUERS or claims.get("aud") != self.client_id:
            raise GoogleError("The ID token is not for this site")
        if not isinstance(claims.get("exp"), int) or claims["exp"] < self._clock():
            raise GoogleError("The ID token has expired")
        if claims.get("email_verified") is not True or not claims.get("email"):
            raise GoogleError("Google has not verified this email address")
        return Identity(subject=str(claims["sub"]), email=str(claims["email"]))


def _claims(token: str) -> dict:
    try:
        payload = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError) as error:
        raise GoogleError("The ID token cannot be read") from error
