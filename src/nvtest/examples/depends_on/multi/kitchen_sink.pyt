import sys
import nvtest

nvtest.directives.depends_on("ingredients.type=*")

def blt() -> int:
    instance = nvtest.get_instance()
    for dep in instance.dependencies:
        assert dep.family == "ingredients"


if __name__ == "__main__":
    sys.exit(blt())
