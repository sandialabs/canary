import os


def main():
    for dir in "abcdefghijklmnopqrstuvwxyz":
        for test in ("t1", "t2", "t3"):
            file = os.path.join("./mock-tests", dir, test + ".pyt")
            os.makedirs(os.path.dirname(file), exist_ok=True)
            with open(file, "w") as fh:
                val = 1 if test == "t1" else 64 if test == "t2" else 0
                fh.write(
                    f"""\
import sys
import time
def main():
    time.sleep(1)
    return {val}
if __name__ == '__main__':
    sys.exit(main())
"""
                )


if __name__ == "__main__":
    main()
