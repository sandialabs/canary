from typing import Optional

import _nvtest

from ..test.file import AbstractTestFile


def analyze(
    *,
    when: Optional[str] = None,
    flag: Optional[str] = None,
    script: Optional[str] = None,
):
    """Create a test instance that depends on all parameterized test instances
    and run it after they have completed.

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import nvtest
       nvtest.directives.analyze(*, flag=None, script=None, when=...)

    ``.vvt``:

    .. code-block:: python

       #VVT: analyze (options=..., platforms=..., testname=...) : (flag|script)

    Parameters
    ----------

    * ``when``: Restrict processing of the directive to this condition
    * ``flag``: Run the test script with the ``--FLAG`` option on the command
      line.  ``flag`` should start with a hyphen (``-``).  The script should
      parse this value and perform the appropriate analysis.
    * ``script``: Run ``script`` during the analysis phase (instead of the test file).

    The ``when`` expression is limited to the following conditions:

    * ``testname``: Restrict processing of the directive to this test name
    * ``platforms``: Restrict processing of the directive to certain platform or
      platforms
    * ``options``: Restrict processing of the directive to command line ``-o`` options
    * ``parameters``: Restrict processing of the directive to certain parameter
      names and values

    References
    ----------

    * :ref:`Writing an execute/analyze test <howto-execute-and-analyze>`

    Examples
    --------

    .. code-block:: python

       import nvtest
       nvtest.directives.analyze(flag="--analyze", when="platforms='not darwin'")
       nvtest.directives.parameterize("a,b", [(1, 2), (3, 4)])

    .. code-block:: python

       # VVT: analyze (platforms="not darwin") : --analyze
       # VVT: parameterize : a,b = 1,2 3,4

    will run an analysis job after jobs ``[a=1,b=3]`` and ``[a=2,b=4]`` have run
    to completion.  The ``nvtest.test.instance`` and ``vvtest_util`` modules
    will contain information regarding the previously run jobs so that a
    collective analysis can be performed.

    For either file type, the script must query the command line arguments to
    determine the type of test to run:

    .. code-block:: python

       import argparse
       import sys

       import nvtest
       nvtest.directives.analyze(flag="--analyze", when="platforms='not darwin'")
       nvtest.directives.parameterize("a,b", [(1, 2), (3, 4)])


       def test() -> int:
           ...

       def analyze() -> int:
           ...

       def main() -> int:
           parser = argparse.ArgumentParser()
           parser.add_argument("--analyze", action="store_true")
           args = parser.parse_args()
           if args.analyze:
               return analyze()
           return test()


       if __name__ == "__main__":
           sys.exit(main())
    """
    if isinstance(_nvtest.__FILE_BEING_SCANNED__, AbstractTestFile):
        file = _nvtest.__FILE_BEING_SCANNED__
        file.m_analyze(when=when, flag=flag, script=script)
