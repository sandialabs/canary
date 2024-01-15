"""
How to write an execute and analyze test
========================================

An execute/analyze test is one that uses parameters to expand into multiple test
instances, followed by a final test instance that analyzes the results.
The analyze test only runs after all the parameter tests are finished.

The addition of the ``nvtest.directives.analyze`` directive marks a test as an
execute/analyze test and will create a separate test for performing the
analysis.

Consider the following test file ``test.pyt`` and associated dependency graph

.. code-block:: python

   import nvtest
   nvtest.directives.analyze()
   nvtest.directives.parameterize("a", [1, 2, 3, 4, 5])

.. code-block:: console

   └── test
   │   ├── test[a=1]
   │   ├── test[a=2]
   │   ├── test[a=3]
   │   ├── test[a=4]
   │   └── test[a=5]

When this test is run, ``test[a=1]``, ..., ``test[a=5]`` are run first and then
``test``.  This last test is the analyze test.

The "children" tests are made available in the
``nvtest.test.instance.dependencies`` attribute.

Example
-------

.. code-block:: python

   import os
   import sys
   import nvtest
   nvtest.directives.analyze()
   nvtest.directives.parameterize("a", [1, 2, 3])

   def test():
       # Run the test
       self = nvtest.test.instance
       f = f'{self.parameters.a}.txt'
       nvtest.filesystem.touchp(f)
       return 0

   def analyze_parameterized_test():
       # Analyze a single parameterized test
       self = nvtest.test.instance
       f = f'{self.parameters.a}.txt'
       assert os.path.exists(f)

   def analyze():
       # Analyze the collective
       self = nvtest.test.instance
       for dep in self.dependencies:
           f = os.path.join(dep.exec_dir, f'{dep.parameters.a}.txt')
           assert os.path.exists(f)

   def main():
       pattern = nvtest.patterns.ExecuteAndAnalyze(
           test_fn=test, verify_fn=analyze_parameterized_test, analyze_fn=analyze
       )
       pattern()
       return 0

   if __name__ == "__main__":
       sys.exit(main())

"""

import os

import _nvtest.util.filesystem as fs


def test_execute_and_analyze(tmpdir):
    from _nvtest.main import NVTestCommand

    with fs.working_dir(tmpdir.strpath, create=True):
        with open("baz.pyt", "w") as fh:
            fh.write(
                """\
import os
import nvtest
nvtest.directives.analyze()
nvtest.directives.parameterize("a", [1, 2, 3])

def test():
    # Run the test
    self = nvtest.test.instance
    f = f'{self.parameters.a}.txt'
    nvtest.filesystem.touchp(f)
    return 0

def analyze_parameterized_test():
    # Analyze a single parameterized test
    self = nvtest.test.instance
    f = f'{self.parameters.a}.txt'
    assert os.path.exists(f)

def analyze():
    # Analyze the collective
    self = nvtest.test.instance
    for dep in self.dependencies:
        f = os.path.join(dep.exec_dir, f'{dep.parameters.a}.txt')
        assert os.path.exists(f)

def main():
    pattern = nvtest.patterns.ExecuteAndAnalyze(
        test_fn=test, verify_fn=analyze_parameterized_test, analyze_fn=analyze
    )
    pattern()
    return 0

if __name__ == '__main__':
    main()
"""
            )
        run = NVTestCommand("run")
        run("-w", ".")
        assert os.path.exists("TestResults/baz.a=1")
        assert os.path.exists("TestResults/baz.a=2")
        assert os.path.exists("TestResults/baz.a=3")
        assert os.path.exists("TestResults/baz")
