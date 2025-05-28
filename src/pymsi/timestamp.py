import datetime

EPOCH = datetime.datetime(1601, 1, 1, tzinfo=datetime.timezone.utc)
EPSILON = 1e-7


def to_datetime(filetime: int):
    return EPOCH + datetime.timedelta(seconds=filetime * EPSILON)


def to_filetime(datetime: datetime.datetime):
    if datetime.tzinfo is None or datetime.tzinfo.utcoffset(datetime) is None:
        raise ValueError("The datetime object must be timezone-aware and in UTC.")
    delta = datetime - EPOCH
    return int(delta.total_seconds() / EPSILON)
