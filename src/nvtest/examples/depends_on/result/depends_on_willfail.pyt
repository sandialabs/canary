import sys
import nvtest

nvtest.directives.depends_on("willfail", result="failed")

def depends_on_willfail() -> int:
    instance = nvtest.get_instance()
    assert instance.dependencies[0].name == "willfail"
    assert instance.dependencies[0].status == "failed"
    print("test passed")
    return 0


if __name__ == "__main__":
    sys.exit(depends_on_willfail())
