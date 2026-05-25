import datetime


def next_wall_clock_datetime(
    now: datetime.datetime,
    hour: int,
    minute: int,
    *,
    include_current_minute: bool = True,
) -> datetime.datetime:
    """Return the next datetime matching a wall-clock hour/minute."""
    if include_current_minute and now.hour == hour and now.minute == minute:
        return now

    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += datetime.timedelta(days=1)
    return candidate


def stop_datetime_after_start(start_at: datetime.datetime, hour: int, minute: int) -> datetime.datetime:
    """Return the next wall-clock stop datetime strictly after a start datetime."""
    candidate = start_at.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= start_at:
        candidate += datetime.timedelta(days=1)
    return candidate


def milliseconds_until(now: datetime.datetime, target: datetime.datetime) -> int:
    return max(0, int((target - now).total_seconds() * 1000))
