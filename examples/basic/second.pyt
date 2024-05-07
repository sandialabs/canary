import sys
import nvtest


nvtest.directives.keywords("basic", "second")
nvtest.directives.link("add.py")


def test():
    add = nvtest.Executable("./add.py")
    output = add("2", "3", output=str)
    assert output.strip() == "5"


if __name__ == "__main__":
    sys.exit(test())
