.. _directive-copy:

copy
====

Copy files from the source directory into the execution directory.

.. code-block:: python

   copy(*args, rename=False, options=None, platforms=None, parameters=None, testname=None)
   copy(src, dst, rename=True, options=None, platforms=None, parameters=None, testname=None)

.. code-block:: python

   #VVT: copy (rename, options=..., platforms=..., parameters=..., testname=...) : args ...

Parameters
----------

* ``args``: File names to copy
* ``rename``: Copy the target file with a different name from the source file
* ``testname``: Restrict processing of the directive to this test name
* ``platforms``: Restrict processing of the directive to certain platform or platforms
* ``options``: Restrict processing of the directive to command line ``-o`` options
* ``parameters``: Restrict processing of the directive to certain parameter names and values

Examples
--------

Copy files ``input.txt`` and ``helper.py`` from the source directory to the execution directory

.. code-block:: python

   import nvtest
   nvtest.mark.copy("input.txt", "helper.py")

.. code-block:: python

   #VVT: copy : input.txt helper.py

----

Copy files ``file1.txt`` and ``file2.txt`` from the source directory to the execution directory and rename them

.. code-block:: python

   import nvtest
   nvtest.mark.copy("file1.txt", "x_file1.txt", rename=True)
   nvtest.mark.copy("file2.txt", "x_file2.txt", rename=True)

.. code-block:: python

   #VVT: copy (rename) : file1.txt,x_file1.txt file2.txt,x_file2.txt
