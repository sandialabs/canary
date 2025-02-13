import os

import pytest

import canary


def test_difflib_unixdiff(tmpdir):
    with pytest.raises(ValueError):
        canary.difflib.unixdiff("spam", "eggs")

    f1 = tmpdir.join("baz.txt")
    f1.write("a b c")

    f2 = tmpdir.join("bar.txt")
    f2.write("a b c")

    with pytest.raises(ValueError):
        canary.difflib.unixdiff("spam", f2.strpath)

    with pytest.raises(ValueError):
        canary.difflib.unixdiff(f1.strpath, "spam")

    canary.difflib.unixdiff(f1.strpath, f2.strpath)

    f2.write("a b c d")
    with pytest.raises(canary.difflib.UnixDiffError):
        canary.difflib.unixdiff(f1.strpath, f2.strpath)


@pytest.mark.skipif(os.getenv("GITLAB_CI") is not None, reason="Fails in gitlab ci")
def test_difflib_imgdiff():
    try:
        from imageio import imread  # noqa: F401
    except ImportError:
        return
    with canary.filesystem.working_dir(os.path.dirname(__file__)):
        canary.difflib.imgdiff("img1.jpg", "img1.jpg")
        with pytest.raises(canary.difflib.ImageDiffError) as excinfo:
            canary.difflib.imgdiff("img1.jpg", "img2.jpg")
        assert "img2.jpg differ" in str(excinfo.value)

        canary.difflib.imgdiff("img1.jpg", "img2.jpg", rtol=0.05)

        with pytest.raises(canary.difflib.ImageDiffError) as excinfo:
            canary.difflib.imgdiff("img2.jpg", "img1.jpg")
        assert "img1.jpg differ" in str(excinfo.value)
        with pytest.raises(canary.difflib.ImageDiffError) as excinfo:
            canary.difflib.imgdiff("img1.jpg", "img3.jpg")
        assert "are different sizes" in str(excinfo.value)

        # For images, canary.difflib.unixdiff calls canary.difflib.imgdiff
        canary.difflib.unixdiff("img1.jpg", "img1.jpg")
        with pytest.raises(canary.difflib.ImageDiffError) as excinfo:
            canary.difflib.unixdiff("img2.jpg", "img1.jpg")
        assert "img1.jpg differ" in str(excinfo.value)
