from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import Request


HKT_TIMEZONE = ZoneInfo("Asia/Hong_Kong")
HKT_TIMEZONE_OFFSET_MINUTES = -8 * 60


def _hkt_today() -> date:
    return datetime.now(HKT_TIMEZONE).date()


@dataclass(frozen=True)
class ClientLocalDay:
    date: date
    timezone_offset_minutes: int = HKT_TIMEZONE_OFFSET_MINUTES

    @property
    def start_utc(self) -> datetime:
        local_start = datetime.combine(self.date, time.min, tzinfo=HKT_TIMEZONE)
        return local_start.astimezone(timezone.utc)

    @property
    def end_utc(self) -> datetime:
        return self.start_utc + timedelta(days=1)

    def utc_bounds(self, start_date: date, end_date: date) -> tuple[datetime, datetime]:
        start = ClientLocalDay(start_date).start_utc
        end = ClientLocalDay(end_date + timedelta(days=1)).start_utc
        return start, end

    def date_for_timestamp(self, value: datetime) -> date:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(HKT_TIMEZONE).date()


_active_client_local_day: ContextVar[ClientLocalDay | None] = ContextVar(
    "active_client_local_day", default=None
)


def get_client_local_day(_request: Request) -> ClientLocalDay:
    return ClientLocalDay(date=_hkt_today())


def bind_client_local_day(request: Request) -> ClientLocalDay:
    client_local_day = get_client_local_day(request)
    _active_client_local_day.set(client_local_day)
    return client_local_day


def get_active_client_local_day() -> ClientLocalDay:
    return _active_client_local_day.get() or ClientLocalDay(date=_hkt_today())