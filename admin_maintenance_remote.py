"""Run retention from GitHub Actions without exporting Neon credentials."""

import asyncio
import os
from urllib.parse import urlencode

import httpx

from retention_auth import authorized_retention

ENDPOINT = "https://english-buddy-telegram.onrender.com/internal/admin-retention"


def cleanup_remote():
    request_url = os.getenv("ACTIONS_ID_TOKEN_REQUEST_URL", "")
    request_token = os.getenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
    if not request_url or not request_token:
        raise SystemExit("GitHub Actions id-token permission is required")
    stage = "GitHub identity"
    try:
        with httpx.Client(timeout=120) as client:
            query = "&" if "?" in request_url else "?"
            response = client.get(
                request_url + query + urlencode({"audience": ENDPOINT}),
                headers={"Authorization": "Bearer " + request_token},
            )
            response.raise_for_status()
            token = response.json()["value"]
            if not asyncio.run(authorized_retention(token, ENDPOINT)):
                raise SystemExit(
                    "GitHub identity does not match the retention contract; no token logged"
                )
            stage = "Render retention"
            result = client.post(ENDPOINT, headers={"Authorization": "Bearer " + token})
            result.raise_for_status()
        print("Render retention completed using short-lived GitHub identity")
    except httpx.HTTPStatusError as exc:
        raise SystemExit(
            f"{stage} failed (HTTP {exc.response.status_code}); no credentials logged"
        ) from None
    except (httpx.HTTPError, ValueError, KeyError):
        # Exception URLs/headers can carry Actions credentials. Never print them.
        raise SystemExit(
            "Remote retention failed; inspect Render health and workflow authorization"
        ) from None


if __name__ == "__main__":
    cleanup_remote()
