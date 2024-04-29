from typing import Optional

import _nvtest

from ..test.file import AbstractTestFile


def enable(*args: bool, when: Optional[str] = None):
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
    if isinstance(_nvtest.__FILE_BEING_SCANNED__, AbstractTestFile):
        arg = True if not args else args[0]
        file = _nvtest.__FILE_BEING_SCANNED__
        file.m_enable(arg, when=when)
