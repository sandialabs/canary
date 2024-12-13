import sys

import nvtest

nvtest.directives.depends_on("ingredients.type=eggs")
nvtest.directives.depends_on("ingredients.type=ham")


def green_eggs_and_ham() -> int:
    instance = nvtest.get_instance()
    for dep in instance.dependencies:
        assert dep.family == "ingredients"
        assert dep.parameters.type in ("eggs", "ham")


if __name__ == "__main__":
    sys.exit(green_eggs_and_ham())
