import difflib
import filecmp
import os

import _nvtest.util.tty as tty
from _nvtest.error import TestDiffed

from .imgdiff import img_diff


def unix_diff(file1, file2, ignore_whitespace=False):
    """Compare files `file1` and `file2` line by line.

    Parameters
    ----------
    file1, file2 : str
        The files to compare

    Returns
    -------
    None
        If the files are the same None is returned

    Raises
    ------
    ValueError
        If `file1` or `file2` cannot be found
    UnixDiffError
        If the files are different

    """
    tty.debug(f"unix_diff: comparing {file1} and {file2}")
    if not os.path.exists(file1):
        raise ValueError(f"unix_diff: file not found: {file1}")
    if not os.path.exists(file2):
        raise ValueError(f"unix_diff: file not found: {file2}")

    if file1.endswith((".jpg", ".png")):
        return img_diff(file1, file2)

    if ignore_whitespace:
        file1, tmp1 = _rewrite_stripped(file1), file1
        file2, tmp2 = _rewrite_stripped(file2), file2

    same = filecmp.cmp(file1, file2)

    if ignore_whitespace:
        os.remove(file1)
        os.remove(file2)
        file1, file2 = tmp1, tmp2

    if not same:
        tty.error("unix_diff: files are different")
        dfunc = difflib.unified_diff
        with open(file1, "rb") as fh1, open(file2, "rb") as fh2:
            diff = difflib.diff_bytes(
                dfunc,
                fh1.readlines(),
                fh2.readlines(),
                encode(file1),
                encode(file2),
                lineterm=b"\n",
            )
        unified_diff = "\n{0}".format("".join(_.decode("utf-8") for _ in diff))
        raise UnixDiffError(unified_diff)


def _rewrite_stripped(file):
    stripped = "\n".join(" ".join(_.split()) for _ in open(file).read() if _.split())
    filename = f".{file}.stripped"
    with open(filename, "w") as fh:
        fh.write(stripped)
    return filename


def encode(string_like):
    return string_like if isinstance(string_like, bytes) else string_like.encode()


class UnixDiffError(TestDiffed):
    ...
