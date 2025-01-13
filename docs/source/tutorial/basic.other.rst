.. _tutorial-basic-other:

Other test file types
=====================

``nvtest`` does not define a specific test file format.  Instead, plugins generate ``nvtest`` recognized test cases:

* The generator is responsible for interpreting the contents of the test file and generating test cases
* Test generators are implemented as :ref:`plugins <extending-plugins>`
* ``nvtest`` ships with builtin generator plugins for ``.pyt``, ``.vvt``, and ``CTestTestfile.cmake`` test files.

The remainder of the tutorial will use ``.pyt`` test files to demonstrate ``nvtest`` functionality.
