"""Shared fixtures for Trading_Bot tests."""

from datetime import datetime
import config as cfg

import pytest


FIXED_NOW = datetime(2024, 1, 1, 12, 0, 5, tzinfo=cfg.TIMEZONE)
FIXED_NOW_S = int(FIXED_NOW.timestamp())


@pytest.fixture
def fixed_now():
    return FIXED_NOW


@pytest.fixture
def patch_datetime_now(monkeypatch):
    """Freeze fetching_data.datetime.now while keeping fromtimestamp real."""
    import fetching_data as fd

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return FIXED_NOW.replace(tzinfo=None)
            return FIXED_NOW.astimezone(tz)

    monkeypatch.setattr(fd, "datetime", FrozenDateTime)
    return FIXED_NOW
