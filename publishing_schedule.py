"""Timezone-aware publication slots, independent of workflow rendering time."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def next_publish_time(slot, now=None):
    if slot not in ('video', 'short'):
        raise ValueError('Publication slot must be video or short')
    eastern = ZoneInfo('America/New_York')
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Publication clock must include a timezone')
    local = now.astimezone(eastern)
    # Leave time for upload and YouTube processing; missed slots roll forward.
    earliest = now + timedelta(minutes=15)
    for offset in range(8):
        day = local.date() + timedelta(days=offset)
        if slot == 'video' and day.weekday() not in (0, 2, 4):
            continue
        candidate = datetime(day.year, day.month, day.day,
                             17 if slot == 'video' else 19, tzinfo=eastern)
        if candidate > earliest:
            return candidate.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    raise ValueError('No publication slot found')
