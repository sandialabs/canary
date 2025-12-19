# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import canary

canary.directives.parameterize("type", ("eggs", "ham", "lettuce", "bacon", "tomato"))


def test():
    instance = canary.get_instance()
    assert instance is not None


if __name__ == "__main__":
    test()
