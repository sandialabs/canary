# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import re
import time
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Callable


def strftimestamp(timestamp: float, fmt: str = "%b %d %H:%M") -> str:
    s = datetime.fromtimestamp(timestamp).strftime(fmt)
    s += f" {time.tzname[1]}"
    return s


def timestamp(local: bool = True) -> float:
    return time.mktime(time.localtime()) if local else time.time()


def time_in_seconds(arg: int | float | str) -> float:
    if isinstance(arg, (float, int)):
        return float(arg)
    duration = Duration.from_str(arg)
    return duration.total_seconds()


def hhmmss(seconds: float | None, threshold: float = 2.0) -> str:
    if seconds is None:
        return "--:--:--"
    t = datetime.fromtimestamp(seconds)
    utc = datetime.fromtimestamp(seconds, timezone.utc)
    if seconds < threshold:
        return datetime.strftime(utc, "%H:%M:%S.%f")[:-4]
    return datetime.strftime(utc, "%H:%M:%S")


def pretty_seconds_formatter(seconds: int | float) -> Callable:
    multiplier: float
    unit: str
    if seconds >= 1:
        multiplier, unit = 1, "s"
    elif seconds >= 1e-3:
        multiplier, unit = 1e3, "ms"
    elif seconds >= 1e-6:
        multiplier, unit = 1e6, "us"
    else:
        multiplier, unit = 1e9, "ns"
    return lambda s: "%.3f%s" % (multiplier * s, unit)


def pretty_seconds(seconds: str | int | float) -> str:
    """Seconds to string with appropriate units

    Arguments:
        seconds (float): Number of seconds

    Returns:
        str: Time string with units
    """
    if isinstance(seconds, str):
        seconds = time_in_seconds(seconds)
    return pretty_seconds_formatter(seconds)(seconds)
    # -*- coding: UTF-8 -*-


class Duration:
    """Support for GO lang's duration format"""

    _nanosecond_size = 1
    _microsecond_size = 1000 * _nanosecond_size
    _millisecond_size = 1000 * _microsecond_size
    _second_size = 1000 * _millisecond_size
    _minute_size = 60 * _second_size
    _hour_size = 60 * _minute_size
    _day_size = 24 * _hour_size
    _week_size = 7 * _day_size
    _month_size = 30 * _day_size
    _year_size = 365 * _day_size

    units = {
        "ns": _nanosecond_size,
        "us": _microsecond_size,
        "µs": _microsecond_size,
        "μs": _microsecond_size,
        "ms": _millisecond_size,
        "s": _second_size,
        "m": _minute_size,
        "h": _hour_size,
        "d": _day_size,
        "w": _week_size,
        "mm": _month_size,
        "y": _year_size,
    }

    _re = re.compile(r"([\d\.]+)([a-zµμ]+)")

    @staticmethod
    def from_str(duration: str) -> timedelta:
        """Parse a duration string to a datetime.timedelta"""

        original = duration

        if not duration:
            return timedelta()
        elif duration in ("0", "+0", "-0"):
            return timedelta()

        sign = 1
        if duration[0] in "+-":
            sign = -1 if duration[0] == "-" else 1
            duration = duration[1:]

        if re.search(r"(?xm)(?:\s|^)([-+]*(?:\d+\.\d*|\.?\d+)(?:[eE][-+]?\d+)?)(?=\s|$)", duration):
            return timedelta(seconds=sign * float(duration))
        elif re.search(r"^\d{1,2}:\d{1,2}:\d{1,2}(\.\d+)?$", duration):
            hours, minutes, seconds = [float(_) for _ in duration.split(":")]
            units = Duration.units
            microseconds = hours * units["h"] + minutes * units["m"] + seconds * units["s"]
            print(microseconds / Duration._microsecond_size)
            return timedelta(microseconds=sign * microseconds / Duration._microsecond_size)
        elif re.search(r"^\d{1,2}:\d{1,2}(\.\d+)?$", duration):
            minutes, seconds = [float(_) for _ in duration.split(":")]
            microseconds = minutes * 60.0 + seconds * 1.0
            return timedelta(microseconds=sign * microseconds / Duration._microsecond_size)

        matches = list(Duration._re.finditer(duration))
        if not matches:
            raise DurationError("Invalid duration {}".format(original))
        if matches[0].start() != 0 or matches[-1].end() != len(duration):
            raise DurationError("Extra chars at start or end of duration {}".format(original))

        total = 0.0
        for match in matches:
            value, unit = match.groups()
            if unit not in Duration.units:
                raise DurationError("Unknown unit {} in duration {}".format(unit, original))
            try:
                total += float(value) * Duration.units[unit]
            except Exception:
                raise DurationError("Invalid value {} in duration {}".format(value, original))

        microseconds = total / Duration._microsecond_size
        return timedelta(microseconds=sign * microseconds)

    @staticmethod
    def to_str(delta: timedelta, extended: bool = False) -> str:
        """Format a datetime.timedelta to a duration string"""

        total_seconds = delta.total_seconds()
        sign = "-" if total_seconds < 0 else ""
        nanoseconds = abs(total_seconds * Duration._second_size)

        if abs(total_seconds) < 1:
            result_str = Duration._to_str_small(nanoseconds, extended)
        else:
            result_str = Duration._to_str_large(nanoseconds, extended)

        return "{}{}".format(sign, result_str)

    @staticmethod
    def _to_str_small(nanoseconds: float, extended: bool) -> str:
        result_str = ""

        if not nanoseconds:
            return "0"

        milliseconds = int(nanoseconds / Duration._millisecond_size)
        if milliseconds:
            nanoseconds -= Duration._millisecond_size * milliseconds
            result_str += "{:g}ms".format(milliseconds)

        microseconds = int(nanoseconds / Duration._microsecond_size)
        if microseconds:
            nanoseconds -= Duration._microsecond_size * microseconds
            result_str += "{:g}us".format(microseconds)

        if nanoseconds:
            result_str += "{:g}ns".format(nanoseconds)

        return result_str

    @staticmethod
    def _to_str_large(nanoseconds: float, extended: bool) -> str:
        result_str = ""

        if extended:
            years = int(nanoseconds / Duration._year_size)
            if years:
                nanoseconds -= Duration._year_size * years
                result_str += "{:g}y".format(years)

            months = int(nanoseconds / Duration._month_size)
            if months:
                nanoseconds -= Duration._month_size * months
                result_str += "{:g}mm".format(months)

            days = int(nanoseconds / Duration._day_size)
            if days:
                nanoseconds -= Duration._day_size * days
                result_str += "{:g}d".format(days)

        hours = int(nanoseconds / Duration._hour_size)
        if hours:
            nanoseconds -= Duration._hour_size * hours
            result_str += "{:g}h".format(hours)

        minutes = int(nanoseconds / Duration._minute_size)
        if minutes:
            nanoseconds -= Duration._minute_size * minutes
            result_str += "{:g}m".format(minutes)

        seconds = float(nanoseconds) / float(Duration._second_size)
        if seconds:
            nanoseconds -= Duration._second_size * seconds
            result_str += "{:g}s".format(seconds)

        return result_str


class DurationError(ValueError):
    """duration error"""
