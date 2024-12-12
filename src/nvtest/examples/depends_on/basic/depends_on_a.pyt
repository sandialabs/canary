import sys
import nvtest

nvtest.directives.depends_on("a")


def depends_on_a():
    instance = nvtest.get_instance()
    assert len(instance.dependencies) == 1
    assert instance.dependencies[0].name == "a"


if __name__ == "__main__":
    sys.exit(depends_on_a())
