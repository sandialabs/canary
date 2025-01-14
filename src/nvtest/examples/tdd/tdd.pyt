import re
import sys

import nvtest

nvtest.directives.keywords("tdd")


def test():
    keyword_expr = nvtest.config.getoption("keyword_expr")
    if not re.search(r"\btdd\b", keyword_expr):
        raise ValueError("Test should not run outside of TDD context")


if __name__ == "__main__":
    sys.exit(test())
