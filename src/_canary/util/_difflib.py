# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import difflib
import filecmp
import os
import sys

from ..error import diff_exit_status


def unix_diff(file1: str, file2: str, ignore_whitespace: bool = False) -> None:
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
    if not os.path.exists(file1):
        raise ValueError(f"unix_diff: file not found: {file1}")
    if not os.path.exists(file2):
        raise ValueError(f"unix_diff: file not found: {file2}")

    if file1.endswith((".jpg", ".png")):
        return img_diff(file1, file2)

    try:
        if ignore_whitespace:
            file1, tmp1 = _rewrite_stripped(file1), file1
            file2, tmp2 = _rewrite_stripped(file2), file2

        same = filecmp.cmp(file1, file2)

    finally:
        if ignore_whitespace:
            os.remove(file1)
            os.remove(file2)
            file1, file2 = tmp1, tmp2

    if not same:
        sys.stderr.write("error: unix_diff: files are different\n")
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


def img_diff(file1: str, file2: str, rtol: float = 1e-4) -> None:
    """Diff two images"""
    # lazy import numpy so that it doesn't slow down importing diffutils if this
    # function is not needed
    import numpy as np
    from imageio import imread

    if not os.path.exists(file1):
        raise ValueError(f"img_diff: file not found: {file1}")
    if not os.path.exists(file2):
        raise ValueError(f"img_diff: file not found: {file2}")

    # read images as 2D arrays (convert to grayscale for simplicity)
    img1 = normalize(to_grayscale(imread(file1).astype(float)))
    img2 = normalize(to_grayscale(imread(file2).astype(float)))

    if not img1.shape == img2.shape:
        raise ImageDiffError(f"Images {file1} and {file2} are different sizes")

    diff = np.sqrt(np.sum((img1 - img2) ** 2)) / img1.size
    if diff > rtol:
        raise ImageDiffError(f"Images {file1} and {file2} differ ({diff})")


def to_grayscale(arr):
    """If arr is a color image (3D array), convert it to grayscale (2D array)."""
    import numpy as np

    if len(arr.shape) == 3:
        # average over the last axis (color channels)
        return np.average(arr, -1)
    else:
        return arr


def normalize(arr):
    rng = arr.max() - arr.min()
    amin = arr.min()
    return (arr - amin) * 255 / rng


class ImageDiffError(Exception):
    exit_code = diff_exit_status


class UnixDiffError(Exception):
    exit_code = diff_exit_status


imgdiff = img_diff
unixdiff = unix_diff
