import os
import subprocess

def grep(pattern):
    p = subprocess.run(f"/usr/bin/grep {pattern} *.rst", shell=True, check=False, text=True, capture_output=True)
    return p.stdout


move = []
for name in os.listdir("_static"):
    s = grep(name).split()
    if len(s) == 0:
        move.append(name)

os.mkdir("trash")
for name in move:
    os.rename(f"_static/{name}", f"trash/{name}")
