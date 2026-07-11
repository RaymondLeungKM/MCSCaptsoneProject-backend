from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from fastapi import Request


@dataclass(frozen=True)
class ClientLocalDay:
    date: date
    timezone_offset_minutes: int

    @property
    def start_utc(self) -> datetime:
        local_start = datetime.combine(self.date, time.min)
        return (local_start + timedelta(minutes=self.timezone_offset_minutes)).replace(
            tzinfo=timezone.utc
        )

    @property
    def end_utc(self) -> datetime:
        return self.start_utc + timedelta(days=1)

    def utc_bounds(self, start_date: date, end_date: date) -> tuple[datetime, datetime]:
        start = ClientLocalDay(start_date, self.timezone_offset_minutes).start_utc
        end = ClientLocalDay(
            end_date + timedelta(days=1), self.timezone_offset_minutes
        ).start_utc
        return start, end

    def date_for_timestamp(self, value: datetime) -> date:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return (value - timedelta(minutes=self.timezone_offset_minutes)).date()


_active_client_local_day: ContextVar[ClientLocalDay | None] = ContextVar(
    "active_client_local_day", default=None
)


def get_client_local_day(request: Request) -> ClientLocalDay:
    raw_date = request.headers.get("x-client-local-date")
    raw_offset = request.headers.get("x-client-timezone-offset-minutes")

    try:
        local_date = date.fromisoformat(raw_date) if raw_date else None
    except ValueError:
        local_date = None

    try:
        timezone_offset_minutes = int(raw_offset) if raw_offset is not None else 0
    except ValueError:
        timezone_offset_minutes = 0

    timezone_offset_minutes = max(min(timezone_offset_minutes, 14 * 60), -12 * 60)
    return ClientLocalDay(
        date=local_date or datetime.now(timezone.utc).date(),
        timezone_offset_minutes=timezone_offset_minutes,
    )


def bind_client_local_day(request: Request) -> ClientLocalDay:
    client_local_day = get_client_local_day(request)
    _active_client_local_day.set(client_local_day)
    return client_local_day


def get_active_client_local_day() -> ClientLocalDay:
    return _active_client_local_day.get() or ClientLocalDay(
        date=datetime.now(timezone.utc).date(),
        timezone_offset_minutes=0,
    )