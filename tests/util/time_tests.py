import _nvtest.util.time as utime


def isclose(a, b, rtol=1e-16, atol=1e-16):
    return abs(a - b) <= (atol + rtol * abs(b))


def test_to_seconds():
    assert isclose(utime.to_seconds("00:01:00"), 60)
    assert isclose(utime.to_seconds("00:00:10"), 10)
    assert isclose(utime.to_seconds("00:00:10.001"), 10.001)
    assert isclose(utime.to_seconds("01:00:00"), 3600)
    assert isclose(utime.to_seconds("s"), 1)
    assert isclose(utime.to_seconds("1 sec"), 1)
    assert isclose(utime.to_seconds("5 secs"), 5)
    assert isclose(utime.to_seconds("5 seconds"), 5)
    assert isclose(utime.to_seconds("minute"), 60)
    assert isclose(utime.to_seconds("1 minute"), 60)
    assert isclose(utime.to_seconds("-1 minute", negatives=True), -60)
    assert isclose(utime.to_seconds("5 minute"), 5 * 60)
    assert isclose(utime.to_seconds("5 minutes"), 5 * 60)
    assert isclose(utime.to_seconds("hour"), 60 * 60)
    assert isclose(utime.to_seconds("1 hour"), 60 * 60)
    assert isclose(utime.to_seconds("5 hour"), 5 * 60 * 60)
    assert isclose(utime.to_seconds("5 hours"), 5 * 60 * 60)
    assert isclose(utime.to_seconds("day"), 24 * 60 * 60)
    assert isclose(utime.to_seconds("1 day"), 24 * 60 * 60)
    assert isclose(utime.to_seconds("2 days"), 2 * 24 * 60 * 60)
    assert isclose(
        utime.to_seconds("1 day 23 hours and 15 mins."), 1 * 24 * 60 * 60 + 23 * 60 * 60 + 15 * 60
    )
    assert isclose(
        utime.to_seconds("1 day - 23 hours and 15 mins."),
        1 * 24 * 60 * 60 - 23 * 60 * 60 + 15 * 60,
    )
    assert isclose(utime.to_seconds(4000), 4000)
    assert isclose(utime.to_seconds(400.0), 400.0)


def test_pretty_seconds():
    assert utime.pretty_seconds("4s") == "4.000s"
    assert utime.pretty_seconds(4) == "4.000s"
    assert utime.pretty_seconds("00:00:10") == "10.000s"
    ten_miliseconds = 0.01
    assert utime.pretty_seconds(ten_miliseconds) == "10.000ms"
    assert utime.pretty_seconds(1e-3 * ten_miliseconds) == "10.000us"
    assert utime.pretty_seconds(1e-6 * ten_miliseconds) == "10.000ns"
