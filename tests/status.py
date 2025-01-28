import _canary.status as status
from _canary.error import diff_exit_status
from _canary.error import fail_exit_status
from _canary.error import skip_exit_status
from _canary.error import timeout_exit_status


def test_status_0():
    stat = status.Status()
    stat.set("failed", details="Just because")
    s = str(stat)
    s = repr(stat)

    other = status.Status()
    assert other != stat
    other.set("failed", details="Just because")
    assert other == stat

    stat.set("ready")
    assert stat.ready()

    stat.set("pending")
    assert stat.pending()

    stat.set_from_code(0)
    assert stat == "success"
    assert stat.name == "PASS"
    stat.set_from_code(diff_exit_status)
    assert stat == "diffed"
    assert stat.name == "DIFF"
    stat.set_from_code(skip_exit_status)
    assert stat == "skipped"
    assert stat.name == "SKIPPED"
    stat.set_from_code(fail_exit_status)
    assert stat == "failed"
    assert stat.name == "FAIL"
    stat.iid
    stat.set_from_code(timeout_exit_status)
    assert stat == "timeout"
    stat.set_from_code(66)
    assert stat == "timeout"
    stat.set_from_code(22)
    assert stat == "failed"

    stat.set("not_run", details="reason")
    assert stat.name == "NOT RUN"
