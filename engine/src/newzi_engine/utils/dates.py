from datetime import datetime, timezone
from dateutil import parser

def parse_date(value) -> datetime | None:
    if not value: return None
    try:
        dt = parser.parse(str(value))
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None

