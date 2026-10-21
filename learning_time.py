"""Use the learner's Turkish calendar day, independent of the hosting region."""

from datetime import datetime
from zoneinfo import ZoneInfo

TURKEY_TZ = ZoneInfo("Europe/Istanbul")


def learning_today():
    return datetime.now(TURKEY_TZ).date()
