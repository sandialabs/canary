from .run_tests import RunTests


class Setup(RunTests):
    description = "Setup tests, but don't run them"
    name = "setup"

    @property
    def mode(self):
        return "write"

    def run(self) -> int:
        self.print_text(f"Tests setup and ready to run in {self.session.rel_workdir}")
        return 0

    def finish(self):
        ...
