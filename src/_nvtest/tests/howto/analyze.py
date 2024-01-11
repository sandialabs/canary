"""
How to run only the analysis section of a test
==============================================

After a test is run, the analysis sections can be run with the ``nvtest analyze``
command

.. code-block:: python

   import os
   import nvtest

   def test():
       # Run the test
       self = nvtest.test.instance
       nvtest.filesystem.touchp(f'{self.name}.txt')
       return 0

   def analyze_parameterized_test():
       # Analyze a single parameterized test
       self = nvtest.test.instance
       f = f'{self.name}.txt'
       assert os.path.exists(f), f"File {os.getcwd()}/{f} not found"

   def main():
       parser = nvtest.make_std_parser()
       args, _ = parser.parse_known_args()
       if args.execute_analysis_sections:
           analyze_parameterized_test()
       else:
           test()
       return 0

   if __name__ == '__main__':
       main()

To execute, first run the tests.  Then, navigate to the test directory and run

.. code-block:: console

   nvtest analyze .

"""

import os
import _nvtest.util.filesystem as fs


def test_analyze(tmpdir):
    from _nvtest.main import NVTestCommand
    with fs.working_dir(tmpdir.strpath, create=True):
        with open("baz.pyt", "w") as fh:
            fh.write("""\
import os
import nvtest

def test():
    # Run the test
    self = nvtest.test.instance
    nvtest.filesystem.touchp(f'{self.name}.txt')
    return 0

def analyze_parameterized_test():
    # Analyze a single parameterized test
    self = nvtest.test.instance
    assert os.path.exists(f'{self.name}.txt')
    nvtest.filesystem.touchp(f'{self.name}.analyzed.txt')

def main():
    parser = nvtest.make_std_parser()
    args, _ = parser.parse_known_args()
    if args.execute_analysis_sections:
        analyze_parameterized_test()
    else:
        test()
    return 0

if __name__ == '__main__':
    main()
""")
        run = NVTestCommand("run")
        run("-w", ".")
        with fs.working_dir("TestResults/baz"):
            analyze = NVTestCommand("analyze")
            analyze.python.add_default_env(NVTEST_DEBUG="1")
            analyze()
            print(os.listdir())
            assert analyze.returncode == 0
            assert os.path.exists("baz.analyzed.txt")
