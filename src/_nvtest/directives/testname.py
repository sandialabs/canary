import _nvtest

from ..test.testfile import AbstractTestFile


def testname(arg: str) -> None:
    """Set the name of a test to one different from the filename and/or define
    multiple test names (multiple test instances) in the same file.

    .. code-block:: python

       pytest.directives.name(arg)

    .. code-block:: python

       testname : arg

    Parameters
    ----------

    * ``arg``: The alternative test name.


    Examples
    --------

    For the test file ``a.vvt`` containing

    .. code-block:: python

       #VVT: testname : spam
       ...

    a test instance with name "spam" would be created, even though the file is
    named ``a.vvt``.

    -------

    ``testname`` can be called multiple times.  Each call will create a new test
    instance with a different name, e.g.

    .. code:: python

       #VVT: testname : foo
       #VVT: testname : bar

       import vvtest_util as vvt

       if vvt.NAME == "foo":
           do_foo_stuff()
       elif vvt.NAME == "bar":
           do_bar_stuff()

    This file would result in two tests: "foo" and "bar".

    """
    if isinstance(_nvtest.__FILE_BEING_SCANNED__, AbstractTestFile):
        file = _nvtest.__FILE_BEING_SCANNED__
        file.m_name(arg)
