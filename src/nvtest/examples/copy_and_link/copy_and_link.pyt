import os

import nvtest

nvtest.directives.copy("copy.txt")
nvtest.directives.link("link.txt")


def test():
    assert os.path.exists("copy.txt") and not os.path.islink("copy.txt")
    assert os.path.exists("link.txt") and os.path.islink("link.txt")
