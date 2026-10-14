import os
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from webapp import external_url, webhook_secret
import webapp


class WebhookTest(unittest.TestCase):
    def test_lifespan_registers_webhook_and_stops_background_tasks(self):
        async def run():
            application = SimpleNamespace(
                initialize=AsyncMock(),start=AsyncMock(),stop=AsyncMock(),shutdown=AsyncMock(),
                bot=SimpleNamespace(token='test-only-token',set_webhook=AsyncMock()),
            )
            server=SimpleNamespace(state=SimpleNamespace())
            with patch.dict(os.environ,{'DATABASE_URL':'test-only-url','WEBHOOK_BASE_URL':'https://testserver'}),patch('webapp.english_bot.build_application',return_value=application),patch('webapp.english_bot.register_commands',new_callable=AsyncMock),patch('webapp.admin_storage',return_value=MagicMock()):
                async with webapp.lifespan(server):
                    self.assertIs(server.state.telegram_application,application)
                    self.assertEqual(application.bot.set_webhook.await_args.kwargs['url'],'https://testserver/telegram/webhook')
                    self.assertFalse(application.bot.set_webhook.await_args.kwargs['drop_pending_updates'])
                application.stop.assert_awaited_once()
                application.shutdown.assert_awaited_once()
        asyncio.run(run())

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
