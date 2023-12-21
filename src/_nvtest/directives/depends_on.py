from typing import Optional

import _nvtest

from ..test.testfile import AbstractTestFile


def depends_on(
    arg: str,
    when: Optional[str] = None,
    expect: Optional[int] = None,
    result: Optional[str] = None,
):
    """
    A test can be made to "depend" on another test. If ``testY`` depends on
    ``testX`` then ``testX`` will be executed before ``testY``. ``testY``
    will have the location of ``testX`` available in its script A dependency is
    added to a test in the test header.

    Usage
    -----

    ``.pyt``:

    .. code:: python

       import nvtest
       nvtest.directives.depends_on("testX")

    ``.vvt``:

    .. code:: python

       #VVT: depends on : testX
       import sys, os

    This test would wait on ``testX`` to complete with a pass or diff result
    status before running. When it does run, the location of ``testY`` is
    provided in a list variable in the **vvtest_util.py** file as

    .. code:: python

       DEPDIRS = ["<path>/testX",]

    where **<path>/testX** is the directory path to the execution of
    ``testX``.

    Conditional execution of a dependent test
    -----------------------------------------

    By default, if a dependency passes or diffs then the dependent test is
    run. However, this can be controlled with the "result" attribute in the
    specification header. For example,

    .. code:: python

       #VVT: depends on (result="pass") : testX
       import sys, os
       ...

    This would only run the dependent test if ``testX`` passed. Expressions
    are allowed, such as "not fail" or "pass or diff". The special value of
    a single asterisk, "*", means run the dependent test no matter what the
    result value is of the dependency test.

    Dependency glob patterns
    ------------------------

    Test dependencies can be specified with shell-style wild cards, such as

    .. code:: python

       #VVT: depends on : testX*param=*

    Tests are matched using the first non-empty list of the following
    methods:

    1. <homedir>/pattern
    2. <homedir>/\*\*/pattern
    3. pattern
    4. \*pattern

    where the <homedir> is the directory containing the test.

    Because a dependency pattern may match more than one test, a second
    variable is placed in the **vvtest_util.py** file for convenience,
    called DEPDIRMAP. It maps the pattern given in the header to an
    alphabetically sorted list of directories (the dependencies).

    Constraining the number of glob matches
    ---------------------------------------

    If no dependency tests are found, then the dependent test will not be
    run (it will be shown as ``notrun`` with reason "failed 'depends on'
    matching criteria"). This behavior can be controlled with the "expect"
    attribute. For example,

    .. code:: python

       #VVT: depends on (expect=2) : foo*bar
       import sys, os
       ...

    This test will only run if the number of tests that match "foo*bar" is
    exactly two. Possible values for "expect" are

    1. ``+`` : one or more matches (this is the default)
    2. ``?`` : zero or one match
    3. ``*`` : zero or more matches
    4. N : a non-negative integer number of matches

    Parameter substitution in dependency patterns
    ---------------------------------------------

    Variable substitutions can be made in the dependency patterns. Use the
    construct "${parameter_name}". For example, suppose the test file
    ``foo.vvt`` had this header:

    .. code:: python

       #VVT: parameterize : pet = dog cat
       #VVT: depends on : store*pet=${pet}*

    Then for the test name **foo.pet=dog**, the dependency pattern will
    resolve to "store*pet=dog\*", and for name **foo.pet=cat** the pattern
    will be "store*pet=cat\*".

    Currently, the substitution is confined to parameter names, and if a the
    dollar-brace construct does not match a parameter name, the pattern is
    left untouched.

    """
    if isinstance(_nvtest.__FILE_BEING_SCANNED__, AbstractTestFile):
        file = _nvtest.__FILE_BEING_SCANNED__
        file.m_depends_on(arg, when=when, result=result, expect=expect)
