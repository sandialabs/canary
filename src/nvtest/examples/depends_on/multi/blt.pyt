import sys
import nvtest

nvtest.directives.depends_on("ingredients.type=bacon")
nvtest.directives.depends_on("ingredients.type=lettuce")
nvtest.directives.depends_on("ingredients.type=tomato")

def blt() -> int:
    instance = nvtest.get_instance()
    for dep in instance.dependencies:
        assert dep.family == "ingredients"
        assert dep.parameters.type in ("bacon", "lettuce", "tomato")


if __name__ == "__main__":
    sys.exit(blt())
