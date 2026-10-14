"""Verify GitHub Actions OIDC for one repository, branch and maintenance job."""

import asyncio
import logging
import time

import httpx
import jwt

ISSUER = "https://token.actions.githubusercontent.com"
REPOSITORY = "huseyink502/english-buddy-telegram"
WORKFLOW = REPOSITORY + "/.github/workflows/admin-retention.yml@refs/heads/main"
_keys = {}
_fetched_at = 0.0
_lock = asyncio.Lock()
LOG = logging.getLogger(__name__)


async def github_keys():
    global _keys, _fetched_at
    async with _lock:
        # Unknown kid never forces another fetch in this cache window.
        if not _keys or time.monotonic() - _fetched_at > 300:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(ISSUER + "/.well-known/jwks")
                response.raise_for_status()
                _keys = {key["kid"]: key for key in response.json()["keys"]}
            _fetched_at = time.monotonic()
        return _keys


async def authorized_retention(token: str, audience: str) -> bool:
    if not token or len(token) > 16000:
        return False
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256":
            return False
        keys = await github_keys()
        data = keys.get(header.get("kid"))
        if data is None:
            return False
        key = jwt.PyJWK.from_dict(data, algorithm="RS256").key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=audience,
            issuer=ISSUER,
            options={
                "require": [
                    "exp",
                    "iat",
                    "nbf",
                    "iss",
                    "aud",
                    "sub",
                    "repository",
                    "ref",
                    "workflow_ref",
                    "event_name",
                ]
            },
        )
        checks = {
            "subject": claims["sub"] == f"repo:{REPOSITORY}:ref:refs/heads/main",
            "repository": claims["repository"] == REPOSITORY,
            "branch": claims["ref"] == "refs/heads/main",
            "workflow": claims["workflow_ref"] == WORKFLOW,
            "event": claims["event_name"] in ("schedule", "workflow_dispatch"),
            "age": 0 <= time.time() - claims["iat"] <= 600,
        }
        rejected = [name for name, passed in checks.items() if not passed]
        if rejected:
            LOG.warning("Retention identity scope rejected (%s)", ",".join(rejected))
        return not rejected
    except (jwt.PyJWTError, KeyError, ValueError, TypeError, httpx.HTTPError) as exc:
        LOG.warning("Retention verification rejected (%s)", type(exc).__name__)
        return False
