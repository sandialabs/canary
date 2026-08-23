# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import canary
import canary_pyt

canary_pyt.directives.parameterize("type", ("eggs", "ham", "lettuce", "bacon", "tomato"))


def test():
    instance = canary.get_instance()
    assert instance is not None


if __name__ == "__main__":
    test()
