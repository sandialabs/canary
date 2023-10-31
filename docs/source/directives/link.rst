.. _directive-link:

link
====

Soft link files from the source directory into the execution directory.

.. code-block:: python

   link(*args, rename=False, options=None, platforms=None, parameters=None, testname=None)
   link(src, dst, rename=True, options=None, platforms=None, parameters=None, testname=None)

.. code-block:: python

   #VVT: link (rename, options=..., platforms=..., parameters=..., testname=...) : args ...

Parameters
----------

* ``args``: File names to link
* ``rename``: Link the target file with a different name from the source file
* ``testname``: Restrict processing of the directive to this test name
* ``platforms``: Restrict processing of the directive to certain platform or platforms
* ``options``: Restrict processing of the directive to command line ``-o`` options
* ``parameters``: Restrict processing of the directive to certain parameter names and values

Examples
--------

Link files ``input.txt`` and ``helper.py`` from the source directory to the execution directory

.. code-block:: python

   import nvtest
   nvtest.mark.link("input.txt", "helper.py")

.. code-block:: python

   #VVT: link : input.txt helper.py

----

Link files ``file1.txt`` and ``file2.txt`` from the source directory to the execution directory and rename them

.. code-block:: python

   import nvtest
   nvtest.mark.link("file1.txt", "x_file1.txt", rename=True)
   nvtest.mark.link("file2.txt", "x_file2.txt", rename=True)

.. code-block:: python

   #VVT: link (rename) : file1.txt,x_file1.txt file2.txt,x_file2.txt
