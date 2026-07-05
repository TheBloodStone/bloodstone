"""Pacific Time helpers for Bloodstone web apps (PST/PDT, US rules)."""

from datetime import datetime, timedelta, timezone


def _dst_start_utc(year):
    """US Pacific DST begins: second Sunday in March at 10:00 UTC."""
    day = datetime(year, 3, 8, 10, tzinfo=timezone.utc)
    while day.weekday() != 6:
        day += timedelta(days=1)
    return day


def _dst_end_utc(year):
    """US Pacific DST ends: first Sunday in November at 09:00 UTC."""
    day = datetime(year, 11, 1, 9, tzinfo=timezone.utc)
    while day.weekday() != 6:
        day += timedelta(days=1)
    return day


def to_pacific(dt):
    """Convert a UTC (or naive-as-UTC) datetime to US Pacific time."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    if _dst_start_utc(dt.year) <= dt < _dst_end_utc(dt.year):
        return dt.astimezone(timezone(timedelta(hours=-7), "PDT"))
    return dt.astimezone(timezone(timedelta(hours=-8), "PST"))


def format_pacific(ts=None, fmt="%Y-%m-%d %H:%M:%S %Z"):
    if ts is None:
        dt = datetime.now(timezone.utc)
    elif isinstance(ts, (int, float)):
        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
    elif isinstance(ts, datetime):
        dt = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        if dt.tzinfo != timezone.utc:
            dt = dt.astimezone(timezone.utc)
    else:
        return "—"
    return to_pacific(dt).strftime(fmt)


def now_pacific(fmt="%Y-%m-%d %H:%M:%S %Z"):
    return format_pacific(None, fmt)