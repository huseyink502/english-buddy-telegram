"""Cryptographically validate the narrowly scoped maintenance identity."""

import json
import time
import unittest
from unittest.mock import MagicMock, patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient

from retention_auth import (
    ISSUER,
    REPOSITORY,
    SUBJECT_PREFIX,
    WORKFLOW,
    authorized_retention,
)
from webapp import app

AUDIENCE = "https://testserver/internal/admin-retention"


class RetentionAuthTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        self.jwk["kid"] = "test"
        self.claims = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": f"{SUBJECT_PREFIX}:ref:refs/heads/main",
            "exp": int(time.time()) + 300,
            "iat": int(time.time()),
            "nbf": int(time.time()),
            "repository": REPOSITORY,
            "ref": "refs/heads/main",
            "workflow_ref": WORKFLOW,
            "event_name": "workflow_dispatch",
        }

    async def test_signature_expiry_audience_repo_branch_and_workflow(self):
        with patch("retention_auth.github_keys", return_value={"test": self.jwk}):

            def token(changes={}):
                return jwt.encode(
                    {**self.claims, **changes},
                    self.key,
                    algorithm="RS256",
                    headers={"kid": "test"},
                )

            self.assertTrue(await authorized_retention(token(), AUDIENCE))
            for changes in (
                {"exp": 0},
                {"aud": "another-service"},
                {"repository": "another/repo"},
                {"ref": "refs/heads/dev"},
                {"sub": "repo:attacker/repo:ref:refs/heads/main"},
                {"sub": f"repo:{REPOSITORY}:ref:refs/heads/main"},
                {"workflow_ref": "another.yml"},
                {"event_name": "pull_request"},
            ):
                self.assertFalse(
                    await authorized_retention(token(changes), AUDIENCE), changes
                )
            forged = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            self.assertFalse(
                await authorized_retention(
                    jwt.encode(
                        self.claims, forged, algorithm="RS256", headers={"kid": "test"}
                    ),
                    AUDIENCE,
                )
            )
            self.assertFalse(
                await authorized_retention(
                    jwt.encode(
                        self.claims,
                        "attacker-secret-with-thirty-two-characters",
                        algorithm="HS256",
                        headers={"kid": "test"},
                    ),
                    AUDIENCE,
                )
            )

    async def test_endpoint_only_cleans_with_verified_identity(self):
        db = MagicMock()
        with (
            patch.dict("os.environ", {"WEBHOOK_BASE_URL": "https://testserver"}),
            patch("webapp.admin_storage", return_value=db),
            patch("retention_auth.github_keys", return_value={"test": self.jwk}),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="https://testserver"
            ) as client:
                response = await client.post("/internal/admin-retention")
                self.assertEqual(response.status_code, 403)
                db.purge_if_due.assert_not_called()
                token = jwt.encode(
                    self.claims, self.key, algorithm="RS256", headers={"kid": "test"}
                )
                response = await client.post(
                    "/internal/admin-retention",
                    headers={"Authorization": "Bearer " + token},
                )
                self.assertEqual(response.status_code, 200)
                db.purge_if_due.assert_called_once()
                db.users.assert_not_called()
                db.conversations.assert_not_called()
