from typing import Optional

import _nvtest

from ..test.testfile import AbstractTestFile


def link(*args: str, when: Optional[str] = None, rename: bool = False):
    """Link files from the source directory into the execution directory.

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       link(*args, rename=False, when=None)
       link(src, dst, rename=True, when=None)

    ``.vvt``:

    .. code-block:: python

       #VVT: link (rename, options=..., platforms=..., parameters=..., testname=...) : args ...

    Parameters
    ----------

    * ``args``: File names to link
    * ``when``: Restrict processing of the directive to this condition
    * ``rename``: Link the target file with a different name from the source file

    Notes
    -----
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
    if isinstance(_nvtest.__FILE_BEING_SCANNED__, AbstractTestFile):
        file = _nvtest.__FILE_BEING_SCANNED__
        file.m_link(*args, when=when)
