# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import canary
import canary_pyt

canary_pyt.directives.name("setup_teardown_example")


@canary_pyt.directives.setup
def my_setup(job: canary.Job) -> None:
    # Runs before the test body, in the job workspace.
    pass


@canary_pyt.directives.teardown
def my_teardown(job: canary.Job) -> None:
    # Runs after the test body, even if it failed.
    pass


def test() -> int:
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(test())
