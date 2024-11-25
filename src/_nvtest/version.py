def get_version_info() -> tuple[str, tuple[int, int, int, str]]:
    import importlib.metadata as im
    import os

    from _nvtest.util.generate_version import version_components_from_git

    f = os.path.join(os.path.dirname(__file__), "../../.git")
    if not os.path.exists(f):
        try:
            version = im.version("nvtest")
            major, minor, remainder = version.split(".", 2)
            patch, *qualifier = remainder.split("+")
            version_tuple: list[int | str] = [int(major), int(minor), int(patch)]
            if qualifier:
                version_tuple.append("+".join(qualifier))
            return version, tuple(version_tuple)
        except im.PackageNotFoundError:
            # if not installed, there won't be any package metadata
            return "unknown", (0, 0, 0, "unknown")
    else:
        major, minor, micro, local = version_components_from_git(full=True)
        version = f"{major}.{minor}.{micro}+{local}"
        version_tuple = (major, minor, micro, local)
        return version, version_tuple


__version__, __version_tuple__ = get_version_info()
version = __version__
version_tuple = __version_tuple__
