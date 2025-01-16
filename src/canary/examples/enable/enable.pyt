import sys

import canary

canary.directives.enable(when="options=enable")


def test():
    pass


if __name__ == "__main__":
    sys.exit(test())
