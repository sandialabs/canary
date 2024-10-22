import glob
import os
import shutil
import sys

dirname = sys.argv[1]
files = glob.glob(f"{dirname}/*.rst")
for src in files:
    basename = os.path.basename(src)
    if basename == "index.rst":
        dst = f"{dirname}.rst"
    else:
        dst = f"{dirname}.{basename}"
    shutil.move(src, dst)
