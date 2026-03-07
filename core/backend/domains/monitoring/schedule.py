from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

PRESET_TO_CRON = {
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@weekly": "0 0 * * 0",
}


@dataclass
class ParsedCron:
    minutes: set[int]
    hours: set[int]
    dom: set[int]
    months: set[int]
    dow: set[int]
    dom_any: bool
    dow_any: bool


def normalize_cron(rule: str) -> str:
    text = (rule or "").strip()
    if not text:
        raise ValueError("schedule_cron is required")
    return PRESET_TO_CRON.get(text, text)


def validate_timezone(name: str) -> str:
    if not name:
        return "UTC"
    try:
        ZoneInfo(name)
    except Exception as exc:
        raise ValueError(f"Invalid timezone: {name}") from exc
    return name


def _expand_range(part: str, min_v: int, max_v: int) -> set[int]:
    part = part.strip()
    if part == "*":
        return set(range(min_v, max_v + 1))

    step = 1
    if "/" in part:
        base, step_text = part.split("/", 1)
        step = int(step_text)
        if step <= 0:
            raise ValueError("Cron step must be > 0")
        part = base

    if part == "*":
        start, end = min_v, max_v
    elif "-" in part:
        start_text, end_text = part.split("-", 1)
        start, end = int(start_text), int(end_text)
    else:
        value = int(part)
        if value < min_v or value > max_v:
            raise ValueError(f"Cron value out of range: {value}")
        return {value}

    if start < min_v or end > max_v or start > end:
        raise ValueError(f"Cron range out of bounds: {part}")
    return set(range(start, end + 1, step))


def _parse_field(field: str, min_v: int, max_v: int) -> tuple[set[int], bool]:
    text = field.strip()
    any_value = text == "*"
    values: set[int] = set()
    for chunk in text.split(","):
        values |= _expand_range(chunk, min_v, max_v)

    if max_v == 7 and 7 in values:
        values.add(0)
        values.remove(7)
    return values, any_value


def parse_cron(rule: str) -> ParsedCron:
    rule = normalize_cron(rule)
    parts = [p for p in rule.split(" ") if p]
    if len(parts) != 5:
        raise ValueError("Cron must have 5 fields: minute hour day month weekday")

    minutes, _ = _parse_field(parts[0], 0, 59)
    hours, _ = _parse_field(parts[1], 0, 23)
    dom, dom_any = _parse_field(parts[2], 1, 31)
    months, _ = _parse_field(parts[3], 1, 12)
    dow, dow_any = _parse_field(parts[4], 0, 7)

    return ParsedCron(
        minutes=minutes,
        hours=hours,
        dom=dom,
        months=months,
        dow=dow,
        dom_any=dom_any,
        dow_any=dow_any,
    )


def _matches(parsed: ParsedCron, dt: datetime) -> bool:
    if dt.minute not in parsed.minutes:
        return False
    if dt.hour not in parsed.hours:
        return False
    if dt.month not in parsed.months:
        return False

    dom_match = dt.day in parsed.dom
    cron_dow = (dt.weekday() + 1) % 7
    dow_match = cron_dow in parsed.dow

    if parsed.dom_any and parsed.dow_any:
        day_ok = True
    elif parsed.dom_any:
        day_ok = dow_match
    elif parsed.dow_any:
        day_ok = dom_match
    else:
        day_ok = dom_match or dow_match

    return day_ok


def next_run_at_utc(
    schedule_cron: str,
    timezone_name: str,
    after_utc: datetime | None = None,
    max_search_days: int = 370,
) -> datetime:
    parsed = parse_cron(schedule_cron)
    timezone_name = validate_timezone(timezone_name)

    raw_after = after_utc or datetime.utcnow()
    if raw_after.tzinfo is None:
        base_utc = raw_after.replace(tzinfo=timezone.utc)
    else:
        base_utc = raw_after.astimezone(timezone.utc)
    tz = ZoneInfo(timezone_name)

    local = base_utc.astimezone(tz)
    cursor = local.replace(second=0, microsecond=0) + timedelta(minutes=1)
    end = cursor + timedelta(days=max_search_days)

    while cursor <= end:
        if _matches(parsed, cursor):
            return cursor.astimezone(timezone.utc).replace(tzinfo=None)
        cursor += timedelta(minutes=1)

    raise ValueError("No next run could be calculated within max search window")


def validate_schedule(schedule_cron: str, timezone_name: str) -> None:
    parse_cron(schedule_cron)
    validate_timezone(timezone_name)
