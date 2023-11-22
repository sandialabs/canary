import os

import _nvtest.util.tty as tty
from _nvtest.error import TestDiffed


def img_diff(file1, file2, rtol=1e-4):
    """Diff two images"""
    # lazy import scipy so that it doesn't slow down import nevada if this
    # function is not needed
    import numpy as np
    from imageio import imread

    tty.debug(f"img_diff: comparing {file1} and {file2}")
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
    from scipy import average

    if len(arr.shape) == 3:
        # average over the last axis (color channels)
        return average(arr, -1)
    else:
        return arr


def normalize(arr):
    rng = arr.max() - arr.min()
    amin = arr.min()
    return (arr - amin) * 255 / rng


class ImageDiffError(TestDiffed):
    ...
