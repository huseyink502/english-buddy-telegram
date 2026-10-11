import os
import unittest
from unittest.mock import patch

from webapp import external_url, webhook_secret


class WebhookTest(unittest.TestCase):
    def test_token_to_webhook_secret(self):
        token = "123456:ABC_some-secret"
        secret = webhook_secret(token)
        self.assertEqual(len(secret), 64)
        self.assertTrue(secret.isalnum())
        self.assertNotEqual(token, secret)
        self.assertEqual(secret, webhook_secret(token))

    def test_render_hostname(self):
        with patch.dict(os.environ, {
            "RENDER_EXTERNAL_HOSTNAME": "english-buddy.onrender.com",
            "WEBHOOK_BASE_URL": "",
        }):
            self.assertEqual(external_url(), "https://english-buddy.onrender.com")

    def test_custom_https_url(self):
        with patch.dict(os.environ, {"WEBHOOK_BASE_URL": "https://abc.example/" }):
            self.assertEqual(external_url(), "https://abc.example")
        with patch.dict(os.environ, {"WEBHOOK_BASE_URL": "http://abc.example" }):
            with self.assertRaises(RuntimeError):
                external_url()


if __name__ == "__main__":
    unittest.main()
