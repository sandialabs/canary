from typing import Optional

import _nvtest

from ..test.file import AbstractTestFile


def depends_on(
    arg: str,
    when: Optional[str] = None,
    expect: Optional[int] = None,
    result: Optional[str] = None,
):
    """
    Require that test ``arg`` run before this test.

    Usage
    -----

    ``.pyt``:

    .. code:: python

       import nvtest
       nvtest.directives.depends_on(name, when=..., expect=None, result=None)

    ``.vvt``:

    .. code:: python

       #VVT: depends on (result=..., expect=..., options=..., platforms=..., testname=...) : arg

    Parameters
    ----------
    * ``arg``: The test that should run before this test.  Wildcards are allowed.
    * ``when``: Restrict processing of the directive to this condition
    * ``result``: Control whether or not this test runs based on the result of the
      dependent test.  By default, a test will run if its dependencies pass or diff.
    * ``expect``: How many dependencies to expect.

    The ``when`` expression is limited to the following conditions:

    * ``testname``: Restrict processing of the directive to this test name
    * ``platforms``: Restrict processing of the directive to certain platform
      or platforms
    * ``options``: Restrict processing of the directive to command line ``-o`` options
    * ``parameters``: Restrict processing of the directive to certain parameter
      names and values

    Examples
    --------

    Run ``spam`` if ``baz`` passes or diffs.

    ``.pyt``:

    .. code-block:: python

       # spam.pyt
       import nvtest
       nvtest.directives.depends_on("baz")

       def test():
           self = nvtest.test.instance
           baz = self.dependencies[0]
           print(f"baz's results can be found in {baz.exec_dir}")

    ``.vvt``:

    .. code-block:: python

       # spam.vvt
       # VVT: depends on: baz
       import vvtest_util as vvt

       def test():
           exec_dir = vvt.DEPDIRS[0]
           print(f"baz's results can be found in {exec_dir}")

    ----------

    Run ``spam`` regardless of ``baz``'s result:

    ``.pyt``:

    .. code-block:: python

       # spam.pyt
       import nvtest
       nvtest.directives.depends_on("baz", result="*")

       def test():
           self = nvtest.test.instance
           baz = self.dependencies[0]
           print(f"baz's results can be found in {baz.exec_dir}")

    ``.vvt``:

    .. code-block:: python

       # spam.vvt
       # VVT: depends on (result=*) : baz
       import vvtest_util as vvt

       def test():
           exec_dir = vvt.DEPDIRS[0]
           print(f"baz's results can be found in {exec_dir}")

    ----------

    ``spam`` depends only on the serial ``baz`` test:

    ``.pyt``:

    .. code-block:: python

       # spam.pyt
       import nvtest
       nvtest.directives.depends_on("baz.np=1")

       def test():
           self = nvtest.test.instance
           baz = self.dependencies[0]
           print(f"baz's results can be found in {baz.exec_dir}")

    ``.vvt``:

    .. code-block:: python

       # spam.vvt
       # VVT: depends on: baz.np=1
       import vvtest_util as vvt

       def test():
           exec_dir = vvt.DEPDIRS[0]
           print(f"baz's results can be found in {exec_dir}")

    """  # noqa: E501
    if isinstance(_nvtest.__FILE_BEING_SCANNED__, AbstractTestFile):
        file = _nvtest.__FILE_BEING_SCANNED__
        file.m_depends_on(arg, when=when, result=result, expect=expect)
