import os


def get_cache_dir(root):
    return os.path.join(root, ".nvtest_cache")


def create_cache_dir(root):
    dir = get_cache_dir(root)
    try:
        os.makedirs(dir, exist_ok=True)
    except Exception:
        return None
    file = os.path.join(dir, "CACHEDIR.TAG")
    if not os.path.exists(file):
        with open(file, "w") as fh:
            fh.write("Signature: 8a477f597d28d172789f06886806bc55\n")
            fh.write("# This file is a cache directory tag automatically created by nvtest.\n")
            fh.write(
                "# For information about cache directory tags see https://bford.info/cachedir/\n"
            )
    return dir
