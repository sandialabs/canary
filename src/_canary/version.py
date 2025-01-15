import importlib.metadata as im
import os


def get_version() -> str:
    from _canary.util.generate_version import version_components_from_git

    f = os.path.join(os.path.dirname(__file__), "../../.git")
    version: str
    if not os.path.exists(f):
        try:
            version = im.version("canary")
        except im.PackageNotFoundError:
            # if not installed, there won't be any package metadata
            version = "0.0.0+unknown"
    else:
        major, minor, micro, local = version_components_from_git(full=True)
        version = f"{major}.{minor}.{micro}+{local}"
    return version


__version__ = version = get_version()
