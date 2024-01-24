import _nvtest

from ..test.testfile import AbstractTestFile


def owners(*args: str):
    """Specify a test's owner[s]

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       owners("name1", "name2", ...)

    ``.vvt``:

    NA

    Parameters
    ----------

    * ``args``: The list of owners

    """
    if isinstance(_nvtest.__FILE_BEING_SCANNED__, AbstractTestFile):
        file = _nvtest.__FILE_BEING_SCANNED__
        file.m_owners(*args)
