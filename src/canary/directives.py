# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""\
Before running a test, ``canary`` reads the test file looking for "test
directives".   Test directives are instructions for how to setup and allocate
resources needed by the test.  The ``.pyt`` and ``.vvt`` file types use
different directive styles.  In the ``.pyt`` file type, directives are python
commands contained in the ``canary.directives`` namespace.  In the ``.vvt`` file
type, text directives are preceded with ``#VVT:`` and ``canary`` will stop
processing further ``#VVT:`` directives once the first non-comment
non-whitespace line has been reached in the test script.

The general format for a directive is

``.pyt``:

.. code-block:: python

   import canary
   canary.directives.directive_name(*args, **kwargs)

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

   <font size="+2"> Conditional directive activation </font>

Most directives take the optional keyword argument ``when``, which is an expression that limits
when the directive is activated.  For example, to restrict a directive to be activated only on
``linux`` platforms, add the following:

.. code-block:: python

   import canary
   canary.directives.directive_name(*args, when='platforms=linux')

or, to restrict processing to ``linux`` platforms and when the user has defined the ``opt`` option
(by passing ``-o opt`` on the command line), add the following:

.. code-block:: python

   import canary
   canary.directives.directive_name(*args, when='platforms=linux options=opt')

``when`` also accepts a ``dict``, so the previous example can be expressed equivalently as

.. code-block:: python

   import canary
   canary.directives.directive_name(*args, when={"platforms": "linux", "options": "opt"})

The ``when`` expression recognizes the following conditions:

``testname``
  Restrict processing of the directive to this test name
``platforms``
  Restrict processing of the directive to certain platform or platforms
``options``
  Restrict processing of the directive to command line -o options
``parameters``
  Restrict processing of the directive to certain parameter names and values

.. raw:: html

   <font size="+3"> Directives: </font>

"""  # noqa: E501

# --------------------------------------- NOTE -------------------------------------------------- #
# This module has empty stubs for each directive.  When a test is loaded, it replaces             #
# (monkeypatches) each method with its own so that side-effects of each directive are applied to  #
# the particular test.                                                                            #
# ----------------------------------------------------------------------------------------------- #

from typing import Any
from typing import Sequence

from _canary import enums

WhenType = str | dict[str, str]


def artifact(file: str, *, when: WhenType | None = None, upon: str = "always") -> None:
    """Save ``file`` as an artifact.  This directive is not used by the test directly.  Reporters
    can save a test's artifacts at their destination.  For instance, the artifacts may submitted to
    CDash as part of the test submission.

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import canary
       canary.directives.artifact(file, *, when=..., upon=...)

    ``.vvt``: ``NA``

    Parameters
    ----------

    * ``when``: Restrict processing of the directive to this condition
    * ``upon``: Define when to save the artifact, based on the status of the job.
      * ``success``: Save artifacts only when the job succeeds.
      * ``failure``: Save artifacts only when the job fails or diffs.
      * ``always``: Always save artifacts (except when jobs time out).

    The ``when`` expression is limited to the following conditions:

    * ``testname``: Restrict processing of the directive to this test name
    * ``platforms``: Restrict processing of the directive to certain platform or
      platforms
    * ``options``: Restrict processing of the directive to command line ``-o`` options
    * ``parameters``: Restrict processing of the directive to certain parameter
      names and values

    Examples
    --------

    .. code-block:: python

       import canary
       canary.directives.artifacts("file.txt", when="platforms='not darwin'", upon="success")
    """


def baseline(
    *,
    src: str | None = None,
    dst: str | None = None,
    when: WhenType | None = None,
    flag: str | None = None,
) -> None:
    """Rebaseline a test by running ``canary rebaseline ...`` in the test session directory (or one of its subdirectories)

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import canary
       canary.directives.baseline(src, dst, when=...)
       canary.directives.baseline(flag=..., when=...)

    ``.vvt``:

    .. code-block:: python

       #VVT: baseline (options=..., platforms=..., testname=...) : src,dst
       #VVT: baseline (options=..., platforms=..., testname=...) : flag

    Parameters
    ----------

    * ``src``: The source file.
    * ``dst``: The destination file to replace with ``src``
    * ``when``: Restrict processing of the directive to this condition
    * ``flag``: Run the test script with the ``--FLAG`` option on the command
      line to perform rebaselining.  ``flag`` should start with a hyphen (``-``).  The script should
      parse this value and perform the appropriate rebaselining.

    The ``when`` expression is limited to the following conditions:

    * ``testname``: Restrict processing of the directive to this test name
    * ``platforms``: Restrict processing of the directive to certain platform or
      platforms
    * ``parameters``: Restrict processing of the directive to certain parameter
      names and values

    Examples
    --------

    .. code-block:: python

       import canary
       canary.directives.baseline("file.exo", "file.base_exo", when="platforms='not darwin'")

    .. code-block:: python

       # VVT: baseline (platforms="not darwin") : file.exo,file.base_exo

    will replace ``file.base_exo`` with ``file.exo`` when the baseline stage is ran in its results directory:

    .. code-block:: console

       $ canary run [options]
       $ cd $(canary -C TestResults location /TESTID)
       $ canary rebaseline .


    """


def copy(
    *files: str,
    src: str | None = None,
    dst: str | None = None,
    when: WhenType | None = None,
) -> None:
    """Copy files from the source directory into the execution directory.

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import canary
       canary.directives.copy(*files, when=...)
       canary.directives.copy(src=..., dst=..., when=...)

    ``.vvt``:

    .. code-block:: python

       #VVT: copy (rename, options=..., platforms=..., parameters=..., testname=...) : files ...

    Parameters
    ----------

    * ``files``: File names to copy
    * ``src``: Source file to copy
    * ``dst``: Copy ``src`` to this destination
    * ``when``: Restrict processing of the directive to this condition

    The ``when`` expression is limited to the following conditions:

    * ``testname``: Restrict processing of the directive to this test name
    * ``platforms``: Restrict processing of the directive to certain platform or
      platforms
    * ``options``: Restrict processing of the directive to command line ``-o`` options
    * ``parameters``: Restrict processing of the directive to certain parameter
      names and values

    .. note::

       The ``files`` positional arguments and ``src,dst`` keyword arguments are mutually exclusive.

    Examples
    --------

    Copy files ``input.txt`` and ``helper.py`` from the source directory to the
    execution directory

    .. code-block:: python

       import canary
       canary.directives.copy("input.txt", "helper.py")

    .. code-block:: python

       #VVT: copy : input.txt helper.py

    ----

    Copy files ``file1.txt`` and ``file2.txt`` from the source directory to the
    execution directory and rename them

    .. code-block:: python

       import canary
       canary.directives.copy(src="file1.txt", dst="file1_copy.txt")
       canary.directives.copy(src="file2.txt", dst="file2_copy.txt")

    .. code-block:: python

       #VVT: copy (rename) : file1.txt,file1_copy.txt file2.txt,file2_copy.txt

    ----

    Copy files ``spam.txt`` and ``eggs.txt`` from the source directory to the
    execution directory if the parameter ``breakfast=spam`` or ``breakfast=eggs``, respectively

    .. code-block:: python

       import canary
       canary.directives.parameterize("breakfast", ("spam", "eggs"))
       canary.directives.copy("spam.txt", when={"parameters": "breakfast=spam"})
       canary.directives.copy("eggs.txt", when={"parameters": "breakfast=eggs"})

    .. code-block:: python

       #VVT: parameterize : breakfast = spam eggs
       #VVT: copy (parameters='breakfast=spam') : spam.txt
       #VVT: copy (parameters='breakfast=eggs') : eggs.txt

    """  # noqa: E501


def depends_on(
    arg: str,
    when: WhenType | None = None,
    expect: int | None = None,
    result: str | None = None,
) -> None:
    """
    Require that test ``arg`` run before this test.

    Usage
    -----

    ``.pyt``:

    .. code:: python

       import canary
       canary.directives.depends_on(name, when=..., expect=None, result=None)

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
       import canary
       canary.directives.depends_on("baz")

       def test():
           self = canary.test.instance
           baz = self.dependencies[0]
           print(f"baz's results can be found in {baz.working directory}")

    ``.vvt``:

    .. code-block:: python

       # spam.vvt
       # VVT: depends on: baz
       import vvtest_util as vvt

       def test():
           working directory = vvt.DEPDIRS[0]
           print(f"baz's results can be found in {working directory}")

    -------

    Run ``spam`` regardless of ``baz``'s result:

    ``.pyt``:

    .. code-block:: python

       # spam.pyt
       import canary
       canary.directives.depends_on("baz", result="*")

       def test():
           self = canary.test.instance
           baz = self.dependencies[0]
           print(f"baz's results can be found in {baz.working directory}")

    ``.vvt``:

    .. code-block:: python

       # spam.vvt
       # VVT: depends on (result=*) : baz
       import vvtest_util as vvt

       def test():
           working directory = vvt.DEPDIRS[0]
           print(f"baz's results can be found in {working directory}")

    -------

    ``spam`` depends only on the serial ``baz`` test:

    ``.pyt``:

    .. code-block:: python

       # spam.pyt
       import canary
       canary.directives.depends_on("baz.cpus=1")

       def test():
           self = canary.test.instance
           baz = self.dependencies[0]
           print(f"baz's results can be found in {baz.working directory}")

    ``.vvt``:

    .. code-block:: python

       # spam.vvt
       # VVT: depends on: baz.np=1
       import vvtest_util as vvt

       def test():
           working directory = vvt.DEPDIRS[0]
           print(f"baz's results can be found in {working directory}")

    """  # noqa: E501


def exclusive(*, when: WhenType | None = None) -> None:
    """Do not run this test in parallel with any other test.

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import canary
       canary.directives.exclusive(*, when=...)

    ``.vvt``: ``NA``

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

    Examples
    --------

    .. code-block:: python

       import canary
       canary.directives.exclusive(when="platforms='not darwin'")
    """


def generate_composite_base_case(
    *,
    when: WhenType | None = None,
    flag: str | None = None,
    script: str | None = None,
) -> None:
    """Create an composite base test case that depends on all of the parameterized test cases
    generated by this file.

    The composite base case will run after all other parameterized test cases and can be used to
    to ensure that the overall behavior of the parameterized test cases.  For example, a parameter
    may represent a step size and the composite base case will verify convergence as the step size
    parameter is reduced.

    The composite base case has access to all of parameterized cases' parameters through the
    ``dependencies`` attribute.

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import canary
       canary.directives.generate_composite_base_case(*, flag=None, script=None, when=...)

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

    * :ref:`Writing an execute/analyze test <usage-execute-and-analyze>`

    Examples
    --------

    .. code-block:: python

       import canary
       canary.directives.generate_composite_base_case(flag="--base", when="platforms='not darwin'")
       canary.directives.parameterize("a,b", [(1, 2), (3, 4)])

    .. code-block:: python

       # VVT: analyze (platforms="not darwin") : --analyze
       # VVT: parameterize : a,b = 1,2 3,4

    will run an analysis job after jobs ``[a=1,b=3]`` and ``[a=2,b=4]`` have run
    to completion.  The ``canary.test.instance`` and ``vvtest_util`` modules
    will contain information regarding the previously run jobs so that a
    collective analysis can be performed.

    For either file type, the script must query the command line arguments to
    determine the type of test to run:

    .. code-block:: python

       import argparse
       import sys

       import canary
       canary.directives.generate_composite_base_case(flag="--base", when="platforms='not darwin'")
       canary.directives.parameterize("a,b", [(1, 2), (3, 4)])


       def test() -> int:
           ...

       def base() -> int:
           ...

       def main() -> int:
           parser = argparse.ArgumentParser()
           parser.add_argument("--base", action="store_true")
           args = parser.parse_args()
           if args.analyze:
               return base()
           return test()


       if __name__ == "__main__":
           sys.exit(main())
    """


analyze = generate_composite_base_case


def enable(*args: bool, when: WhenType | None = None) -> None:
    """
    Explicitly mark a test to be enabled (or not)

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import canary
       canary.directives.enable(arg, when=...)

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

       import canary
       canary.directives.enable(False)

    .. code-block:: python

       #VVT: enable : false

    ----

    Enable the test if the platform name is not "ATS"

    .. code-block:: python

       import canary
       canary.directives.enable(True, when="platforms='not ATS'")

    .. code-block:: python

       #VVT: enable (platform="not ATS") : true

    ----

    More examples:

    .. code-block:: python

       import canary
       canary.directives.enable(True, when="testname=foo platform='Darwin or Linux'")
       canary.directives.enable(True, when="platform='not Windows' options='not debug'")
       canary.directives.enable(False, when="testname=foo")

    The above examples are equivalent to:

    .. code-block:: python

       import canary
       canary.directives.enable(True, when={"testname": "foo", "platform": "Darwin or Linux"})
       canary.directives.enable(True, when={"platform": "not Windows", "options": "not debug"})
       canary.directives.enable(False, when={"testname": "foo"})

    The ``vvt`` equivalent are

    .. code-block:: python

       #VVT: enable (testname=foo, platform="Darwin or Linux") : true
       #VVT: enable (platform="not Windows", options="not debug") : true
       #VVT: enable (testname=foo) : false

    """  # noqa: E501


def include(file: str, *, when: WhenType | None = None) -> None:
    r"""Include the contents of ``file`` at the point where the directive appears.

    Usage
    -----

    ``.pyt``: ``NA``

    ``.vvt``:

    .. code-block:: python

       #VVT: include (options=..., platforms=...) : file
       #VVT: insert directive file (options=..., platforms=...) : file

    Parameters
    ----------

    * ``file``: The file to include
    * ``when``: Restrict processing of the directive to this condition

    The ``when`` expression is limited to the following conditions:

    * ``platforms``: Restrict processing of the directive to certain platform or platforms
    * ``options``: Restrict processing of the directive to command line ``-o`` options

    Notes
    -----

    * ``include``\ d files can ``include`` other files
    * If ``file`` is a relative path, it is assumed relative to the file ``includ``\ing it
    * The alias ``insert directive file`` is also recognized

    Examples
    --------

    .. code-block:: python

       # VVT: include : file.txt

    will include directives from ``file.txt`` into the current test.

    """


def keywords(*args: str, when: WhenType | None = None) -> None:
    """Mark a test with keywords.  The main use of test keywords is to filter a
    set of tests, such as selecting which tests to run.

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import canary
       canary.directives.keywords(*args, when=...)

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

         import canary
         canary.directives.parameterize("meshsize", (0.1, 0.01, 0.001))

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

       import canary
       canary.directives.keywords("3D", "mhd", "circuit")

    .. code-block:: python

       #VVT: keywords : 3D mhd circuit

    ----

    .. code-block:: python

       import canary
       canary.directives.keywords("3D", "mhd", when="testname=spam parameters='cpus>1'")

    .. code-block:: python

       #VVT: keywords (testname=spam, parameters="np>1") : 3D mhd
    """


def link(
    *files: str,
    src: str | None = None,
    dst: str | None = None,
    when: WhenType | None = None,
) -> None:
    """Link files from the source directory into the execution directory.

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import canary
       canary.directives.link(*files, when=...)
       canary.directives.link(src=..., dst=..., when=...)

    ``.vvt``:

    .. code-block:: python

       #VVT: link (rename, options=..., platforms=..., parameters=..., testname=...) : files ...

    Parameters
    ----------

    * ``files``: File names to link
    * ``src``: Source file to link
    * ``dst``: Link ``src`` to this destination
    * ``when``: Restrict processing of the directive to this condition

    The ``when`` expression is limited to the following conditions:

    * ``testname``: Restrict processing of the directive to this test name
    * ``platforms``: Restrict processing of the directive to certain platform or
      platforms
    * ``options``: Restrict processing of the directive to command line ``-o`` options
    * ``parameters``: Restrict processing of the directive to certain parameter
      names and values

    .. note::

       The ``files`` positional arguments and ``src,dst`` keyword arguments are mutually exclusive.

    Examples
    --------

    Link files ``input.txt`` and ``helper.py`` from the source directory to the
    execution directory

    .. code-block:: python

       import canary
       canary.directives.link("input.txt", "helper.py")

    .. code-block:: python

       #VVT: link : input.txt helper.py

    ----

    Link files ``file1.txt`` and ``file2.txt`` from the source directory to the
    execution directory and rename them

    .. code-block:: python

       import canary
       canary.directives.link(src="file1.txt", dst="file1_link.txt")
       canary.directives.link(src="file2.txt", dst="file2_link.txt")

    .. code-block:: python

       #VVT: link (rename) : file1.txt,file1_link.txt file2.txt,file2_link.txt

    """  # noqa: E501


def owners(*args: str) -> None:
    """Specify a test's owner[s]

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import canary
       canary.directives.owners("name1", "name2", ...)

    ``.vvt``: ``NA``

    Parameters
    ----------

    * ``args``: The list of owners

    """


owner = owners


def parameterize(
    names: str | Sequence[str],
    values: Sequence[Sequence[Any] | Any],
    *,
    when: WhenType | None = None,
    type: enums.enums = enums.list_parameter_space,
    samples: int = 10,
    random_seed: float = 1234.0,
) -> None:
    """Add new invocations to the test using the list of argvalues for the given
    argnames.

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import canary
       canary.directives.parametrize(argnames, argvalues, when=..., type=None)


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
    * ``samples``: (``.pyt`` only) Generate this many random elements
      (applicable only if ``type=canary.random_parameter_space``)

    The ``when`` expression is limited to the following conditions:

    * ``testname``: Restrict processing of the directive to this test name
    * ``platform``: Restrict processing of the directive to certain platform or platforms
    * ``option``: Restrict processing of the directive to command line ``-o`` options

    Special argnames
    ----------------

    * ``cpus`` interpreted to mean "number of processing cores".
      If the ``cpus`` parameter is not defined, the test is assumed to use 1
      processing core.
    * ``gpus`` interpreted to mean "number of gpus".
      If the ``gpus`` parameter is not defined, the test is assumed to use 0
      gpus.

    References
    ----------

    * :ref:`Parameterizing Tests <usage-parameterize>`

    Examples
    --------

    The following equivalent test specifications result in 4 test instantiations

    ``test1.pyt``:

    .. code-block:: python

       # test1
       canary.directives.parameterize("cpus", (4, 8, 12, 32))

    ``test1.vvt``:

    .. code-block:: python

       # test1
       #VVT: parameterize : np = 4 8 12 32

    .. code-block:: console

       4 test cases:
       ├── test1[cpus=4]
       ├── test1[cpus=8]
       ├── test1[cpus=12]
       ├── test1[cpus=32]

    ----

    ``argnames`` can be a list of parameters with associated ``argvalues``, e.g.

    ``test1.pyt``:

    .. code-block:: python

       # test1
       canary.directives.parameterize("a,b", ((1, 2), (3, 4), (5, 6)))

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
       canary.directives.parameterize("a,b", [("a1", "b1"), ("a2", "b2")])
       canary.directives.parameterize("x", ["x1", "x2"])

    results in the following test invocations:

    .. code-block:: console

       4 test cases:
       ├── test1[a=a1,b=b1,x=x1]
       ├── test1[a=a1,b=b1,x=x2]
       ├── test1[a=a2,b=b2,x=x1]
       ├── test1[a=a2,b=b2,x=x2]

    """  # noqa: E501


def preload(arg: str, *, when: WhenType | None = None, source: bool = False) -> None:
    """Load shell shell script before test execution

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import canary
       canary.directives.preload(arg, *, when=..., source=False):

    ``.vvt``:

    .. code-block:: python

       # VVT: preload (options=..., platforms=..., testname=...) : [source-script] script_name

    .. warning::

       The ``preload`` currently has no effect.  Use ``canary.shell.source`` instead,
       see :ref:`usage-rcfiles`.


    """


def load_module(name: str, *, use: str | None = None, when: WhenType | None = None) -> None:
    """Load a module before a test is executed.

    Usage
    -----

    ``.pyt``:

    .. code:: python

       import canary
       canary.directives.load_module(name, when=..., use=...)

    ``.vvt``: ``NA``

    Parameters
    ----------

    * ``name``: The name of the module
    * ``use``: Add this directory to ``MODULEPATH``
    * ``when``: Restrict processing of the directive to this condition

    Examples
    --------

    .. code:: python

       import sys
       import canary
       canary.directives.load_module("gcc")

    will load the ``gcc`` module before the test is executed.

    """


def source(name: str, *, when: WhenType | None = None) -> None:
    """Source a shell rc file before a test is executed.

    Usage
    -----

    ``.pyt``:

    .. code:: python

       import canary
       canary.directives.source(name, when=...)

    ``.vvt``: ``NA``

    Parameters
    ----------

    * ``name``: The name of the rc file
    * ``when``: Restrict processing of the directive to this condition

    Examples
    --------

    .. code:: python

       import sys
       import canary
       canary.directives.source("setup-env.sh")

    will source the ``setup-env.sh`` file before the test is executed.

    """


def set_attribute(*, when: WhenType | None = None, **attributes: Any) -> None:
    """Set an attribute on the test

    Usage
    -----

    ``.pyt``:

    .. code:: python

       import canary
       canary.directives.set_attribute(*, when=..., **attributes)

    ``.vvt``: ``NA``

    Parameters
    ----------

    * ``when``: Restrict processing of the directive to this condition
    * ``attributes``: ``attr:value`` pairs

    Examples
    --------

    .. code:: python

       import sys
       import canary
       canary.directives.set_attribute(program="program_name")

    will set the attribute ``program`` on the test case with value "program_name".

    """


def skipif(arg: bool, *, reason: str) -> None:
    """Conditionally skip tests

    Usage
    -----

    ``.pyt``:

    .. code:: python

       import canary
       canary.directives.skipif(arg, *, reason)

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
       import canary
       canary.directives.skipif(
           sys.platform == "Darwin", reason="Test does not run on Apple"
       )

    .. code:: python

       #VVT: skipif (reason=Test does not run on Apple) : sys.platform == "Darwin"

    will skip the test if run on Apple hardware.

    If ``reason`` is not defined, ``canary`` reports the reason as
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


def sources(*args: str, when: WhenType | None = None) -> None:
    pass


def stages(*args: str) -> None:
    pass


def testname(arg: str) -> None:
    """Set the name of a test to one different from the filename and/or define
    multiple test names (multiple test instances) in the same file.

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import canary
       canary.directives.name(arg)

    ``.vvt``:

    .. code-block:: python

       testname : arg

    Parameters
    ----------

    * ``arg``: The alternative test name.

    Examples
    --------

    For the test file ``a.pyt`` containing

    .. code-block:: python

       import canary
       canary.directives.testname("spam")
       ...

    a test instance with name "spam" would be created, even though the file is
    named ``a.pyt``.

    -------

    ``testname`` can be called multiple times.  Each call will create a new test
    instance with a different name, e.g.

    ``.pyt``:

    .. code:: python

       import canary
       canary.directives.testname("foo")
       canary.directives.testname("bar")

       def test():
           self = canary.get_instance()
           if self.name == "foo":
               do_foo_stuff()
           elif self.name == "bar":
               do_bar_stuff()

    ``.vvt``:

    .. code:: python

       #VVT: testname : foo
       #VVT: testname : bar

       import vvtest_util as vvt

       def test():
           if vvt.NAME == "foo":
               do_foo_stuff()
           elif vvt.NAME == "bar":
               do_bar_stuff()

    This file would result in two tests: "foo" and "bar".

    """


name = testname


def timeout(arg: str | float | int, *, when: WhenType | None = None) -> None:
    """Specify a timeout value for a test

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import canary
       canary.directives.timeout(arg, when=...)

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


def xdiff(*, when: WhenType | None = None) -> None:
    """The test is expected to diff.

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import canary
       canary.directives.xdiff(when=...)

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


def xfail(*, code: int = -1, when: WhenType | None = None) -> None:
    """The test is expected to fail (return with a non-zero exit code).  If
    ``code > 0`` and the exit code is not ``code``, the test will be considered
    to have failed.

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import canary
       canary.directives.xfail(code=-1, when=...)

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
