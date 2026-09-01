import sys

import canary
import canary_pyt

canary_pyt.directives.set_attribute(example=True)


def test():
    self = canary.get_instance()
    assert isinstance(self, canary.TestInstance)
    assert self.attributes["example"] is True
    return 0


if __name__ == "__main__":
    sys.exit(test())
