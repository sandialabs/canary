from .run_tests import RunTests


class Setup(RunTests):
    """Setup tests, but don't run them"""

    @property
    def mode(self):
        return self.Mode.WRITE

    def run(self) -> int:
        self.print_text(f"Tests setup and ready to run in {self.rel_workdir}")
        return 0

    def teardown(self):
        ...
