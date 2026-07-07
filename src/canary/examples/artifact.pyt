import sys

import canary

canary.directives.artifact("summary.txt", save_on="always")


def test():
    with open("summary.txt", "w") as fh:
        fh.write("artifact example\n")
    return 0


if __name__ == "__main__":
    sys.exit(test())
