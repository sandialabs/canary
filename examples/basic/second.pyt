import sys
import nvtest


nvtest.directives.keywords("basic", "second")
nvtest.directives.link("add.py")


def test():
    print("Verifying that 2 + 3 = 5")
    add = nvtest.Executable("./add.py")
    result = add("2", "3", stdout=str)
    assert int(result.get_output()) == 5, "Bummer, test failed."
    print("Test passed!")


if __name__ == "__main__":
    sys.exit(test())
