"""Retention cleanup, usable by the running app and scheduled GitHub Actions."""

import asyncio
import logging
import os

from admin_store import AdminStore

LOG = logging.getLogger(__name__)


async def maintenance_loop(store):
    while True:
        try:
            await asyncio.to_thread(store.purge_if_due)
        except Exception:
            LOG.warning("Admin retention storage temporarily unavailable")
        await asyncio.sleep(3600)


def cleanup():
    url = os.getenv("DATABASE_URL_UNPOOLED") or os.getenv("DATABASE_URL", "")
    if not url:
        raise SystemExit("DATABASE_URL is required for retention cleanup")
    store = AdminStore(url)
    store.setup()
    store.purge_if_due()


if __name__ == "__main__":
    cleanup()
