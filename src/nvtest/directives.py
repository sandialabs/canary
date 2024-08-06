"""\
Before running a test, ``nvtest`` reads the test file looking for "test
directives".   Test directives are instructions for how to setup and allocate
resources needed by the test.  The ``.pyt`` and ``.vvt`` file types use
different directive styles.  In the ``.pyt`` file type, directives are python
commands contained in the ``nvtest.directives`` namespace.  In the ``.vvt`` file
type, text directives are preceded with ``#VVT:`` and ``nvtest`` will stop
processing further ``#VVT:`` directives once the first non-comment
non-whitespace line has been reached in the test script.

The general format for a directive is

``.pyt``:

.. code-block:: python

   import nvtest
   nvtest.directives.directive_name(*args, **kwargs)

``.vvt``:

.. code-block:: python

    #VVT: directive_name [<option spec>] [: <args>]

where the optional ``option spec`` takes the form:

.. code-block:: console

    (name=value[, ...])

``.vvt`` directives can be continued on subsequent lines by starting them with ``#VVT::``:

.. code-block:: python

    #VVT: directive_name : args
    #VVT:: ...
    #VVT:: ...

Which is equivalent to

.. code-block:: python

    #VVT: directive_name : args ... ...

.. raw:: html

   <font size="+3"> Available test directives:</font>

"""  # noqa: E501

# ---------------------------------------- NOTE ------------------------------------------------- #
# This module has empty stubs for each directive.  When a test is loaded, it replaces             #
# (monkeypatches) each method with its own so that side-effects of each directive are applied to  #
# the particular test.                                                                            #
# ----------------------------------------------------------------------------------------------- #

from typing import Any
from typing import Optional
from typing import Sequence
from typing import Union

from _nvtest import enums


def analyze(
    *,
    when: Optional[str] = None,
    flag: Optional[str] = None,
    script: Optional[str] = None,
) -> None:
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


def copy(*args: str, when: Optional[str] = None, rename: bool = False) -> None:
    """Copy files from the source directory into the execution directory.

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import nvtest
       nvtest.directives.copy(*args, rename=False, when=...)
       nvtest.directives.copy(src, dst, rename=True, when=...)

    ``.vvt``:

    .. code-block:: python

       #VVT: copy (rename, options=..., platforms=..., parameters=..., testname=...) : args ...

    Parameters
    ----------

    * ``args``: File names to copy
    * ``when``: Restrict processing of the directive to this condition
    * ``rename``: Copy the target file with a different name from the source file

    The ``when`` expression is limited to the following conditions:

    * ``testname``: Restrict processing of the directive to this test name
    * ``platforms``: Restrict processing of the directive to certain platform or
      platforms
    * ``options``: Restrict processing of the directive to command line ``-o`` options
    * ``parameters``: Restrict processing of the directive to certain parameter
      names and values

    Examples
    --------

    Copy files ``input.txt`` and ``helper.py`` from the source directory to the
    execution directory

    .. code-block:: python

       import nvtest
       nvtest.directives.copy("input.txt", "helper.py")

    .. code-block:: python

       #VVT: copy : input.txt helper.py

    ----

    Copy files ``file1.txt`` and ``file2.txt`` from the source directory to the
    execution directory and rename them

    .. code-block:: python

       import nvtest
       nvtest.directives.copy("file1.txt", "x_file1.txt", rename=True)
       nvtest.directives.copy("file2.txt", "x_file2.txt", rename=True)

    .. code-block:: python

       #VVT: copy (rename) : file1.txt,x_file1.txt file2.txt,x_file2.txt

    """  # noqa: E501


def depends_on(
    arg: str,
    when: Optional[str] = None,
    expect: Optional[int] = None,
    result: Optional[str] = None,
) -> None:
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


def gpus(*ngpus: int, when: Optional[str] = None) -> None:
    """Run the test with this many gpus

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import nvtest
       nvtest.directives.gpus(*ngpus, when=...)


    ``.vvt``: NA

    Parameters
    ----------

    * ``ngpus``: List of gpu counts
    * ``when``: Restrict processing of the directive to this condition

    The ``when`` expression is limited to the following conditions:

    * ``testname``: Restrict processing of the directive to this test name
    * ``platform``: Restrict processing of the directive to certain platform or
      platforms
    * ``option``: Restrict processing of the directive to command line ``-o`` options

    Notes
    -----

    * ``gpus(...)`` is equivalent to ``parameterize("ngpu", ...)``

    Examples
    --------

    The following equivalent test specifications result in 4 test instantiations

    ``test1.pyt``:

    .. code-block:: python

       # test1
       nvtest.directives.gpus(1, 2)

    .. code-block:: console

       2 test cases:
       ├── test1[ngpu=1]
       ├── test1[ngpu=2]

    """


devices = gpus


def enable(*args: bool, when: Optional[str] = None) -> None:
    """
    Explicitly mark a test to be enabled (or not)

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import nvtest
       nvtest.directives.enable(arg, when=...)

    ``.vvt``:

    .. code-block:: python

       #VVT: enable (options=..., platforms=..., testname=...) : arg

    Parameters
    ----------
    * ``arg``: Optional (default: ``True``).  If ``True``, enable the test.  If ``False``, disable the test
    * ``when``: Restrict processing of the directive to this condition

    The ``when`` expression is limited to the following conditions:

    * ``testname``: Restrict processing of the directive to this test name
    * ``platforms``: Restrict processing of the directive to certain platform or platforms
    * ``options``: Restrict processing of the directive to command line ``-o`` options
    * ``parameters``: Restrict processing of the directive to certain parameter names and values

    Examples
    --------

    Explicitly disable a test

    .. code-block:: python

       import nvtest
       nvtest.directives.enable(False)

    .. code-block:: python

       #VVT: enable : false

    ----

    Enable the test if the platform name is not "ATS"

    .. code-block:: python

       import nvtest
       nvtest.directives.enable(True, when="platforms='not ATS'")

    .. code-block:: python

       #VVT: enable (platform="not ATS") : true

    ----

    More examples:

    .. code-block:: python

       import nvtest
       nvtest.directives.enable(True, when="testname=foo platform='Darwin or Linux'")
       nvtest.directives.enable(True, when="platform='not Windows' options='not debug'")
       nvtest.directives.enable(False, when="testname=foo")

    The above examples are equivalent to:

    .. code-block:: python

       import nvtest
       nvtest.directives.enable(True, when={"testname": "foo", "platform": "Darwin or Linux"})
       nvtest.directives.enable(True, when={"platform": "not Windows", "options": "not debug"})
       nvtest.directives.enable(False, when={"testname": "foo"})

    The ``vvt`` equivalent are

    .. code-block:: python

       #VVT: enable (testname=foo, platform="Darwin or Linux") : true
       #VVT: enable (platform="not Windows", options="not debug") : true
       #VVT: enable (testname=foo) : false

    """  # noqa: E501


def keywords(*args: str, when: Optional[str] = None) -> None:
    """Mark a test with keywords.  The main use of test keywords is to filter a
    set of tests, such as selecting which tests to run.

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import nvtest
       nvtest.directives.keywords(*args, when=...)

    ``.vvt``:

    .. code-block:: python

       #VVT: keywords (parameters=..., testname=...) : args...

    Parameters
    ----------

    * ``args``: list of keywords
    * ``when``: Restrict processing of the directive to this condition

    The ``when`` expression is limited to the following conditions:

    * ``testname``: Restrict processing of the directive to this test name
    * ``parameters``: Restrict processing of the directive to certain parameter
      names and values

    Implicit keywords
    -----------------

    The following implicit keywords are defined:

    * The test name
    * The test file basename (regardless of testname settings)
    * The names of parameters, e.g.

      .. code-block::

         import nvtest
         nvtest.directives.parameterize("meshsize", (0.1, 0.01, 0.001))

      would have "meshsize" as a keyword.
    * The results of running the test are added as keywords. The result strings are
       * ``ready``: the test is ready to be run
       * ``pass`` : the test ran and completed successfully
       * ``diff`` : the test ran and completed with a numerical difference
       * ``fail`` : the test ran but crashed for some reason (exited with a
         non-zero exit status)
       * ``timeout`` : the test ran out of time and was killed.  A test that
         times out is also considered to have failed.

    Examples
    --------

    .. code-block:: python

       import nvtest
       nvtest.directives.keywords("3D", "mhd", "circuit")

    .. code-block:: python

       #VVT: keywords : 3D mhd circuit

    ----

    .. code-block:: python

       import nvtest
       nvtest.directives.keywords("3D", "mhd", when="testname=spam parameters='np>1'")

    .. code-block:: python

       #VVT: keywords (testname=spam, parameters="np>1") : 3D mhd
    """


def link(*args: str, when: Optional[str] = None, rename: bool = False) -> None:
    """Link files from the source directory into the execution directory.

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import nvtest
       nvtest.directives.link(*args, rename=False, when=...)
       nvtest.directives.link(src, dst, rename=True, when=...)

    ``.vvt``:

    .. code-block:: python

       #VVT: link (rename, options=..., platforms=..., parameters=..., testname=...) : args ...

    Parameters
    ----------

    * ``args``: File names to link
    * ``when``: Restrict processing of the directive to this condition
    * ``rename``: Link the target file with a different name from the source file

    The ``when`` expression is limited to the following conditions:

    * ``testname``: Restrict processing of the directive to this test name
    * ``platforms``: Restrict processing of the directive to certain platform or
      platforms
    * ``options``: Restrict processing of the directive to command line ``-o`` options
    * ``parameters``: Restrict processing of the directive to certain parameter
      names and values

    Examples
    --------

    Link files ``input.txt`` and ``helper.py`` from the source directory to the
    execution directory

    .. code-block:: python

       import nvtest
       nvtest.directives.link("input.txt", "helper.py")

    .. code-block:: python

       #VVT: link : input.txt helper.py

    ----

    Link files ``file1.txt`` and ``file2.txt`` from the source directory to the
    execution directory and rename them

    .. code-block:: python

       import nvtest
       nvtest.directives.link("file1.txt", "x_file1.txt", rename=True)
       nvtest.directives.link("file2.txt", "x_file2.txt", rename=True)

    .. code-block:: python

       #VVT: link (rename) : file1.txt,x_file1.txt file2.txt,x_file2.txt

    """  # noqa: E501


def owners(*args: str) -> None:
    """Specify a test's owner[s]

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import nvtest
       nvtest.directives.owners("name1", "name2", ...)

    ``.vvt``:

    NA

    Parameters
    ----------

    * ``args``: The list of owners

    """


def parameterize(
    names: Union[str, Sequence[str]],
    values: list[Union[Sequence[object], object]],
    *,
    when: Optional[str] = None,
    type: enums.enums = enums.list_parameter_space,
) -> None:
    """Add new invocations to the test using the list of argvalues for the given
    argnames.

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import nvtest
       nvtest.directives.parametrize(argnames, argvalues, when=..., type=None)


    ``.vvt``:

    .. code-block:: python

       #VVT: parametrize (options=...,platforms=...,testname=...) : argnames = argvalues

    Parameters
    ----------

    * ``argnames``: A comma-separated string denoting one or more argument
      names, or a list/tuple of argument strings.
    * ``argvalues``: If only one ``argname`` was specified, ``argvalues`` is a
      list of values.  If ``N`` ``argnames`` were specified, ``argvalues`` is a
      2D list of values where each column are the values for its respective
      ``argname``.
    * ``when``: Restrict processing of the directive to this condition
    * ``type``: (``.pyt`` only) Generate parameters using this type

    The ``when`` expression is limited to the following conditions:

    * ``testname``: Restrict processing of the directive to this test name
    * ``platform``: Restrict processing of the directive to certain platform or platforms
    * ``option``: Restrict processing of the directive to command line ``-o`` options

    Special argnames
    ----------------

    * ``np`` interpreted to mean "number of processing cores".
      If the ``np`` parameter is not defined, the test is assumed to use 1
      processing core.
    * ``ngpu`` interpreted to mean "number of gpus".
      If the ``ngpu`` parameter is not defined, the test is assumed to use 0
      gpus.

    References
    ----------

    * :ref:`Parameterizing Tests <howto-parameterize>`

    Examples
    --------

    The following equivalent test specifications result in 4 test instantiations

    ``test1.pyt``:

    .. code-block:: python

       # test1
       nvtest.directives.parameterize("np", (4, 8, 12, 32))

    ``test1.vvt``:

    .. code-block:: python

       # test1
       #VVT: parameterize : np = 4 8 12 32

    .. code-block:: console

       4 test cases:
       ├── test1[np=4]
       ├── test1[np=8]
       ├── test1[np=12]
       ├── test1[np=32]

    ----

    ``argnames`` can be a list of parameters with associated ``argvalues``, e.g.

    ``test1.pyt``:

    .. code-block:: python

       # test1
       nvtest.directives.parameterize("a,b", ((1, 2), (3, 4), (5, 6)])

    ``test1.vvt``:

    .. code-block:: python

       # test1
       #VVT: parameterize : a,b = 1,2 3,4 5,6

    .. code-block:: console

       3 test cases:
       ├── test1[a=1,b=2]
       ├── test1[a=3,b=4]
       ├── test1[a=5,b=6]

    ----

    ``parameterize`` can be called multiple times.  When multiple parameterize
    directives are given, the Cartesian product of each is taken to form the set
    of parameters, e.g.

    ``test1.pyt``:

    .. code-block:: python

       # test1
       nvtest.directives.parameterize("a,b", [("a1", "b1"), ("a2", "b2")])
       nvtest.directives.parameterize("x", ["x1", "x2"])

    results in the following test invocations:

    .. code-block:: console

       4 test cases:
       ├── test1[a=a1,b=b1,x=x1]
       ├── test1[a=a1,b=b1,x=x2]
       ├── test1[a=a2,b=b2,x=x1]
       ├── test1[a=a2,b=b2,x=x2]

    """  # noqa: E501


def preload(arg: str, *, when: Optional[str] = None, source: bool = False) -> None:
    """Load shell shell script before test execution

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import nvtest
       nvtest.directives.preload(arg, *, when=..., source=False):

    ``.vvt``:

    .. code-block:: python

       # VVT: preload ([source]) : arg

    .. warning::

       The ``preload`` currently has no effect.  Use ``nvtest.shell.source`` instead,
       see :ref:`howto-environ`.


    """


def cpus(*values: int, when: Optional[str] = None) -> None:
    """Run the test with this many processors

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import nvtest
       nvtest.directives.cpus(*nprocs, when=...)


    ``.vvt``: NA

    Parameters
    ----------

    * ``nprocs``: List of processor counts
    * ``when``: Restrict processing of the directive to this condition

    The ``when`` expression is limited to the following conditions:

    * ``testname``: Restrict processing of the directive to this test name
    * ``platform``: Restrict processing of the directive to certain platform or
      platforms
    * ``option``: Restrict processing of the directive to command line ``-o`` options

    Notes
    -----

    * ``cpus(...)`` is equivalent to ``parameterize("np", ...)``

    Examples
    --------

    The following test specification result in 4 test instantiations

    ``test1.pyt``:

    .. code-block:: python

       # test1
       nvtest.directives.cpus(4, 8, 12, 32)

    .. code-block:: console

       4 test cases:
       ├── test1[np=4]
       ├── test1[np=8]
       ├── test1[np=12]
       ├── test1[np=32]

    """


processors = cpus


def nodes(*values: int, when: Optional[str] = None) -> None:
    """Run the test with this many processors

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import nvtest
       nvtest.directives.nodes(*nnode, when=...)


    ``.vvt``: NA

    Parameters
    ----------

    * ``nnodes``: List of node counts
    * ``when``: Restrict processing of the directive to this condition

    The ``when`` expression is limited to the following conditions:

    * ``testname``: Restrict processing of the directive to this test name
    * ``platform``: Restrict processing of the directive to certain platform or
      platforms
    * ``option``: Restrict processing of the directive to command line ``-o`` options

    Notes
    -----

    * ``nodes(...)`` is equivalent to ``parameterize("nnode", ...)``

    Examples
    --------

    The following test specification result in 4 test instantiations

    ``test1.pyt``:

    .. code-block:: python

       # test1
       nvtest.directives.nodes(4, 8, 12, 32)

    .. code-block:: console

       4 test cases:
       ├── test1[nnode=4]
       ├── test1[nnode=8]
       ├── test1[nnode=12]
       ├── test1[nnode=32]

    """


def set_attribute(*, when: Optional[str] = None, **attributes: Any) -> None:
    """Set an attribute on the test

    Usage
    -----

    ``.pyt``:

    .. code:: python

       import nvtest
       nvtest.directives.set_attribute(*, when=..., **attributes)

    ``.vvt``: NA

    Parameters
    ----------

    * ``when``: Restrict processing of the directive to this condition
    * ``attributes``: ``attr:value`` pairs

    Examples
    --------

    .. code:: python

       import sys
       import nvtest
       nvtest.directives.set_attribute(program="program_name")

    will set the attribute ``program`` on the test case with value "program_name".

    """


def skipif(arg: bool, *, reason: str) -> None:
    """Conditionally skip tests

    Usage
    -----

    ``.pyt``:

    .. code:: python

       import nvtest
       nvtest.directives.skipif(arg, *, reason)

    ``.vvt``:

    .. code:: python

       #VVT: skipif : python_expression

    Parameters
    ----------

    * ``arg``: If ``True``, the test will be skipped.
    * ``reason``: The reason the test is being skipped.

    .vvt Parameters
    ---------------

    * ``python_expression``: String that is evaluated and cast to a ``bool``. If
      the result is ``True`` the test will be skipped.

    Examples
    --------

    .. code:: python

       import sys
       import nvtest
       nvtest.directives.skipif(
           sys.platform == "Darwin", reason="Test does not run on Apple"
       )

    .. code:: python

       #VVT: skipif (reason=Test does not run on Apple) : sys.platform == "Darwin"

    will skip the test if run on Apple hardware.

    If ``reason`` is not defined, ``nvtest`` reports the reason as
    ``"python_expression evaluated to True"``.

    Checking module availability
    ----------------------------

    A test may be skipped if a module is not importable by using the
    ``importable`` function. ``importable(module_name)`` evaluates to ``True``
    if ``module_name`` can be imported otherwise, ``False``. For example,

    .. code-block:: python

       #VVT: skipif : not importable("numpy")

    would skip the test if ``numpy`` was not available.

    Evaluation namespace
    --------------------

    ``python_expression`` is evaluated in a minimal namespace consisting of the
    ``os`` module, ``sys`` module, and ``importable`` function.

    """


def sources(*args: str, when: Optional[str] = None) -> None:
    pass


def testname(arg: str) -> None:
    """Set the name of a test to one different from the filename and/or define
    multiple test names (multiple test instances) in the same file.

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import nvtest
       pytest.directives.name(arg)

    ``.vvt``:

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


name = testname


def timeout(arg: Union[str, float, int], *, when: Optional[str] = None) -> None:
    """Specify a timeout value for a test

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import nvtest
       nvtest.directives.timeout(arg, when=...)

    ``.vvt``:

    .. code-block:: python

       # VVT: timeout (options=..., platforms=..., parameters=..., testname=...) : arg

    Parameters
    ----------

    * ``arg``: The time in seconds.  Natural language forms such as "20m", "1h
      20m", and HH:MM:SS such as "2:30:00" are also allowed and converted to
      seconds.
    * ``when``: Restrict processing of the directive to this condition

    The ``when`` expression is limited to the following conditions:

    * ``testname``: Restrict processing of the directive to this test name
    * ``platforms``: Restrict processing of the directive to certain platform or
      platforms
    * ``options``: Restrict processing of the directive to command line ``-o`` options
    * ``parameters``: Restrict processing of the directive to certain parameter
      names and values

    """


def xdiff(*, when: Optional[str] = None) -> None:
    """The test is expected to diff.

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import nvtest
       nvtest.directives.xdiff(when=...)

    Parameters
    ----------

    * ``when``: Restrict processing of the directive to this condition

    The ``when`` expression is limited to the following conditions:

    * ``testname``: Restrict processing of the directive to this test name
    * ``platforms``: Restrict processing of the directive to certain platform or
      platforms
    * ``options``: Restrict processing of the directive to command line ``-o`` options
    * ``parameters``: Restrict processing of the directive to certain parameter
      names and values

    """


def xfail(*, code: int = -1, when: Optional[str] = None) -> None:
    """The test is expected to fail (return with a non-zero exit code).  If
    ``code > 0`` and the exit code is not ``code``, the test will be considered
    to have failed.

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import nvtest
       nvtest.directives.xfail(code=-1, when=...)

    Parameters
    ----------

    * ``code``: The expected return code.  ``-1`` considers any non-zero return code to be a pass.
    * ``when``: Restrict processing of the directive to this condition

    The ``when`` expression is limited to the following conditions:

    * ``testname``: Restrict processing of the directive to this test name
    * ``platforms``: Restrict processing of the directive to certain platform or
      platforms
    * ``options``: Restrict processing of the directive to command line ``-o`` options
    * ``parameters``: Restrict processing of the directive to certain parameter
      names and values

    """
