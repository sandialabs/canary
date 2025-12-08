# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import canary

canary.directives.parameterize("type", ("eggs", "ham", "lettuce", "bacon", "tomato"))


def test():
    instance = canary.get_instance()
    if instance.parameters["type"] == "bacon":
        assert 0


# if __name__ == "__main__":
#    test()
