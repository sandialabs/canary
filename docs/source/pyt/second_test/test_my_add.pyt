import sys
import nvtest

nvtest.directives.link("my-add")

def test() -> int:
    my_add = nvtest.Executable("./my-add")
    out = my_add("3", "2", output=str)
    assert my_add.returncode == 0
    assert int(out.strip()) == 5
    return 0


if __name__ == "__main__":
    sys.exit(test())
