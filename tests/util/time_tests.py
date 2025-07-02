# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from _canary.plugins.builtin.vvtest import to_seconds
from _canary.util.time import pretty_seconds
from _canary.util.time import time_in_seconds


def isclose(a, b, rtol=1e-16, atol=1e-16):
    return abs(a - b) <= (atol + rtol * abs(b))


def test_to_seconds():
    assert isclose(to_seconds("00:01:00"), 60)
    assert isclose(to_seconds("00:00:10"), 10)
    assert isclose(to_seconds("00:00:10.001"), 10.001)
    assert isclose(to_seconds("01:00:00"), 3600)
    assert isclose(to_seconds("s"), 1)
    assert isclose(to_seconds("1 sec"), 1)
    assert isclose(to_seconds("5 secs"), 5)
    assert isclose(to_seconds("5 seconds"), 5)
    assert isclose(to_seconds("minute"), 60)
    assert isclose(to_seconds("1 minute"), 60)
    assert isclose(to_seconds("-1 minute", negatives=True), -60)
    assert isclose(to_seconds("5 minute"), 5 * 60)
    assert isclose(to_seconds("5 minutes"), 5 * 60)
    assert isclose(to_seconds("hour"), 60 * 60)
    assert isclose(to_seconds("1 hour"), 60 * 60)
    assert isclose(to_seconds("5 hour"), 5 * 60 * 60)
    assert isclose(to_seconds("5 hours"), 5 * 60 * 60)
    assert isclose(to_seconds("day"), 24 * 60 * 60)
    assert isclose(to_seconds("1 day"), 24 * 60 * 60)
    assert isclose(to_seconds("2 days"), 2 * 24 * 60 * 60)
    assert isclose(
        to_seconds("1 day 23 hours and 15 mins."), 1 * 24 * 60 * 60 + 23 * 60 * 60 + 15 * 60
    )
    assert isclose(
        to_seconds("1 day - 23 hours and 15 mins."),
        1 * 24 * 60 * 60 - 23 * 60 * 60 + 15 * 60,
    )
    assert isclose(to_seconds(4000), 4000)
    assert isclose(to_seconds(400.0), 400.0)


def test_pretty_seconds():
    assert pretty_seconds("4s") == "4.000s"
    assert pretty_seconds(4) == "4.000s"
    assert pretty_seconds("00:00:10") == "10.000s"
    ten_miliseconds = 0.01
    assert pretty_seconds(ten_miliseconds) == "10.000ms"
    assert pretty_seconds(1e-3 * ten_miliseconds) == "10.000us"
    assert pretty_seconds(1e-6 * ten_miliseconds) == "10.000ns"


def test_time_in_seconds():
    assert isclose(time_in_seconds("00:01:00"), 60)
    assert isclose(time_in_seconds("00:00:10"), 10)
    assert isclose(time_in_seconds("00:00:10.001"), 10.001)
    assert isclose(time_in_seconds("01:00:00"), 3600)
    assert isclose(time_in_seconds("1"), 1)
    assert isclose(time_in_seconds("1.0"), 1)
    assert isclose(time_in_seconds("1."), 1)
    assert isclose(time_in_seconds("1.e+00"), 1)
    assert isclose(time_in_seconds("+1.e+00"), 1)
    assert isclose(time_in_seconds("-1.e+00"), -1)
    assert isclose(time_in_seconds("-1.e0"), -1)
    assert isclose(time_in_seconds("1s"), 1)
    assert isclose(time_in_seconds("5s"), 5)
    assert isclose(time_in_seconds("1m"), 60)
    assert isclose(time_in_seconds("-1m"), -60)
    assert isclose(time_in_seconds("5m"), 5 * 60)
    assert isclose(time_in_seconds("1h"), 60 * 60)
    assert isclose(time_in_seconds("5h"), 5 * 60 * 60)
    assert isclose(time_in_seconds("1d"), 24 * 60 * 60)
    assert isclose(time_in_seconds("2d"), 2 * 24 * 60 * 60)
    assert isclose(time_in_seconds("1d23h15m"), 1 * 24 * 60 * 60 + 23 * 60 * 60 + 15 * 60)
    assert isclose(time_in_seconds(4000), 4000)
    assert isclose(time_in_seconds(400.0), 400.0)
