import time
from typing import Final


ISO_FORMAT_TIMESTAMP_TZ: Final[str] = "%Y-%m-%dT%H:%M:%S%z"


def format_iso_timestamp_tz(seconds: float) -> str:
    """
    Formats the given time in seconds since epoch as a iso timestamp string with time zone.
    Returns None if the given time is empty.

    Args:
        seconds (float): the time in seconds since epoch
    Returns:
        str: the iso timestamp string with time zone
    """
    result: str = None
    if time:
        result = time.strftime(ISO_FORMAT_TIMESTAMP_TZ, time.localtime(seconds))
    return result


def parse_iso_timestamp_tz(string: str) -> float:
    """
    Parses the given iso timestamp string with time zone as a time in seconds since epoch.
    Returns None if the given string is empty.
    If the string cannot be parsed, ValueError is raised.

    Args:
        string (str): the iso timestamp string with time zone
    Returns:
        float: the time in seconds since epoch
    """
    result: float = None
    if string:
        result = time.mktime(time.strptime(string, ISO_FORMAT_TIMESTAMP_TZ))
    return result
