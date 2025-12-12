#!/usr/bin/env python3
import os
import sys

import canary

canary.directives.parameterize("a", ("link_when_1", "link_when_2"))
canary.directives.parameterize("b", (1, 2))
canary.directives.link("link_when_2.txt", when={"parameters": "a=link_when_2 and b=1"})
canary.directives.link("link_when_1.txt", when='parameters="a=link_when_1 and b=1"')
canary.directives.link(
    src="link_when_2.txt", dst="link_when_2-b2.txt", when={"parameters": "a=link_when_2 and b=2"}
)
canary.directives.link(
    src="link_when_1.txt", dst="link_when_1-b2.txt", when='parameters="a=link_when_1 and b=2"'
)


def test():
    self = canary.get_instance()
    if self.parameters[("a", "b")] == ("link_when_2", 1):
        assert os.path.islink("link_when_2.txt")
    elif self.parameters[("a", "b")] == ("link_when_1", 1):
        assert os.path.islink("link_when_1.txt")
    elif self.parameters[("a", "b")] == ("link_when_2", 2):
        assert os.path.islink("link_when_2-b2.txt")
    elif self.parameters[("a", "b")] == ("link_when_1", 2):
        assert os.path.islink("link_when_1-b2.txt")


if __name__ == "__main__":
    sys.exit(test())
