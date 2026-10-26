# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import pytest

from _canary.core.job import Dependency


class DummyStatus:
    category = type("C", (), {"name": "PASS"})()
    outcome = type("O", (), {"name": "SUCCESS"})()


class DummyJob:
    status = DummyStatus()

    def is_done(self) -> bool:
        return True


def test_dependency_when_rejects_unknown_on_keyword() -> None:
    dep = Dependency(job=DummyJob(), when="on_sucess")

    with pytest.raises(ValueError, match="Unknown dependency when"):
        dep.is_satisfied()
