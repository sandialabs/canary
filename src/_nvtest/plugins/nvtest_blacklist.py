import os
import sys

try:
    import yaml
except ImportError:
    yaml = None

from typing import Any
from typing import Union

import nvtest
from _nvtest.session import Session
from _nvtest.test import TestCase
from _nvtest.util import tty
from _nvtest.util.executable import Executable
from _nvtest.util.singleton import Singleton


class Blacklist:
    """Determine if a test has been blacklisted, or not

    Tests call the function `blacklisted` from `vvtest_user_plugin.validate_test`
    that is called by `vvtest` for each test.

    Notes
    -----
    As a way to blacklist a test, they can be added to a file `blacklist.yaml` in
    any directory searched by vvtest.  The layout of `blacklist.yaml` is:

    .. code-block:: yaml

        blacklist:
        - "file": str,
          Optional("case"): str,
          Optional("required_imports"): list_of_required_imports,
          Optional("when"): python_expr,
          Optional("reason"): str

    - The `reason` field is optional iff `required_imports` and `when` are not
      specified.

    Examples
    --------

    .. code-block:: yaml

       blacklist:
       - file: some_test
         reason: "some_test is skipped unconditionally"
       - file: some_other_test
         required_imports:
         - scipy.linalg
       - file: another_test
         case: np=2
         when: os.getenv('SNLSYSTEM') == "cts1"
         reason: "another_test is troublesome with np=2 on cts1"

    """

    root = "blacklist"

    def __init__(self):
        self.cache = {}
        if yaml is None:
            tty.warn("Failed to import yaml, blacklist will be ignored")

    @property
    def filename(self):
        return f"{self.root}.yaml"

    def load_db_for_case(self, case: TestCase) -> Union[None, dict]:
        dirname = os.path.join(case.file_root, case.file_path)
        while True:
            if dirname in self.cache:
                return self.cache[dirname]
            f = os.path.join(dirname, self.filename)
            if os.path.exists(f):
                data = self.load(f)
                if data:
                    self.cache[dirname] = data
                    return data
            if dirname == case.file_root:
                break
            dirname = os.path.dirname(dirname)
        return None

    def load(self, filename: str) -> Union[dict, None]:
        if yaml is None:
            return None
        with open(filename) as fh:
            data = yaml.safe_load(fh)
            if self.root not in data:
                tty.error(f"missing field {self.root!r} in {filename}")
                return None
        return data[self.root]

    def find(self, case: TestCase) -> Union[dict, None]:
        """Finds a specific test in the db"""
        db = self.load_db_for_case(case)
        if db is None:
            return None
        for blacklisted in db:
            file = blacklisted["file"]
            if case.file_path == file:
                break
            elif os.path.join(case.file_root, case.file_path).endswith(file):
                break
        else:
            return None
        if "case" not in blacklisted:
            return blacklisted
        elif isinstance(blacklisted["case"], str):
            blacklisted["case"] = [blacklisted["case"]]
        for bcase in blacklisted["case"]:
            if case.fullname == bcase:
                return blacklisted
        return None

    def get(self, case: TestCase) -> Union[str, None]:
        """If the test described in `spec` is blacklisted, return the reason why

        Parameters
        ----------
        spec : TestSpec
            The vvtest TestSpec instance

        Returns
        -------
        reason : None or str
            If None, the test is not blacklisted, else the reason why the test is
            blacklisted

        """
        blacklisted = self.find(case)
        if blacklisted is None:
            return None

        if "required_imports" in blacklisted:
            failed_imports = self.check_required_imports(
                blacklisted["required_imports"]
            )
            if not failed_imports:
                return None
            s = "s" if len(failed_imports) > 1 else ""
            failed = ", ".join(failed_imports)
            reason = f"failed to import required module{s} ({failed})"

        elif "when" in blacklisted:
            when = blacklisted["when"]
            skip = evaluate_boolean_expression(when)
            if not skip:
                return None
            reason = blacklisted.get("reason", f"{when!r} evaluated to True")

        elif "reason" in blacklisted:
            # Unconditionally blacklisted
            reason = blacklisted["reason"]

        else:
            tty.warn(f"{case.family}: no reason given for skipping")
            reason = "Skipped due to blacklist"

        return f"blacklisted: {reason}"

    def check_required_imports(self, required_imports):
        failed_imports = []
        python_exe = Executable(sys.executable)
        kwds = dict(fail_on_error=False, output=str, error=str)
        for required_import in required_imports:
            python_exe("-c", f"import {required_import}", **kwds)
            if python_exe.returncode != 0:
                failed_imports.append(required_import)
        return failed_imports


def evaluate_boolean_expression(expression):
    import os  # noqa
    import sys  # noqa

    # Variables exist so they can be used in evaluation
    compiler_vendor = compiler_version = None
    compiler_spec = None
    if compiler_spec:
        compiler_vendor, compiler_version = compiler_spec.split("@")
    build_type = None  # noqa: F841
    snlsystem = os.getenv("SNLSYSTEM")  # noqa: F841
    try:
        result = eval(expression)
    except Exception:
        tty.warn(f"{expression!r} failed to evaluate")
        result = None
    return bool(result)


_blacklist = Singleton(Blacklist)


@nvtest.plugin.register("blacklist", scope="test", stage="setup")
def blacklisted(session: Session, case: TestCase, **kwargs: Any) -> None:
    if case.skip:
        return
    reason = _blacklist.get(case)
    if reason is not None:
        case.skip = reason
