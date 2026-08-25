.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Environment Handling
====================

Environment Variables
---------------------

The ``ENVIRONMENT`` property sets environment variables for tests:

.. code-block:: cmake

   add_test(my_test "my_program")
   set_tests_properties(my_test PROPERTIES ENVIRONMENT "VAR1=value1;VAR2=value2")

Environment Modification
------------------------

The ``ENVIRONMENT_MODIFICATION`` property modifies existing environment variables:

.. code-block:: cmake

   add_test(my_test "my_program")
   set_tests_properties(my_test PROPERTIES
     ENVIRONMENT_MODIFICATION "PATH=prepend:/new/path;VAR=set:value")

Supported Operations
~~~~~~~~~~~~~~~~~~~

+----------------------------+--------------------------------------------------+
| Operation                  | Description                                      |
+============================+==================================================+
| ``set``                    | Set variable to value                            |
+----------------------------+--------------------------------------------------+
| ``unset``                  | Remove variable                                  |
+----------------------------+--------------------------------------------------+
| ``string_append``          | Append string to variable                        |
+----------------------------+--------------------------------------------------+
| ``string_prepend``         | Prepend string to variable                       |
+----------------------------+--------------------------------------------------+
| ``path_list_append``       | Append to PATH-style variable                    |
+----------------------------+--------------------------------------------------+
| ``path_list_prepend``      | Prepend to PATH-style variable                   |
+----------------------------+--------------------------------------------------+
| ``cmake_list_append``      | Append to CMake list variable                    |
+----------------------------+--------------------------------------------------+
| ``cmake_list_prepend``     | Prepend to CMake list variable                   |
+----------------------------+--------------------------------------------------+

Examples
~~~~~~~~

.. code-block:: cmake

   set_tests_properties(my_test PROPERTIES
     ENVIRONMENT_MODIFICATION
       "PATH=path_list_prepend:/usr/local/bin"
       "LD_LIBRARY_PATH=path_list_append:/usr/local/lib"
       "MY_VAR=string_append:_suffix"
       "TEMP_VAR=unset:")

Environment Variable Processing
--------------------------------

Environment processing follows this order:

1. **Base Environment**: System environment variables
2. **ENVIRONMENT**: Variables from ``ENVIRONMENT`` property
3. **ENVIRONMENT_MODIFICATION**: Modifications from ``ENVIRONMENT_MODIFICATION`` property
4. **Resource Groups**: Variables from resource group allocation

Working Directory
------------------

The ``WORKING_DIRECTORY`` property sets the test execution directory:

.. code-block:: cmake

   add_test(my_test "my_program")
   set_tests_properties(my_test PROPERTIES WORKING_DIRECTORY "/path/to/workdir")

Canary executes the test command in the specified directory:

.. code-block:: bash

   cd /path/to/workdir && exec command

See Also
--------

- :doc:`overview` - Extension overview
- :doc:`ctest-properties` - Property reference
- :doc:`resources` - Resource group variables