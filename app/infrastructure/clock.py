"""Clock adapter implementing ClockPort."""

from datetime import UTC, datetime

from app.domain.ports import ClockPort


class SystemUtcClock(ClockPort):
    """Production clock adapter returning current timezone-aware UTC datetime."""

    def now_utc(self) -> datetime:
        return datetime.now(UTC)
