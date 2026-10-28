.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

VVTest File Format
==================

VVTest files use the ``.vvt`` extension and contain directives in ``#VVT:`` comments. These directives are parsed by ``canary_vvtest`` and converted to Canary job specifications.

File Structure
--------------

A typical ``.vvt`` file follows this pattern:

.. code-block:: text

   #VVT: directive1 : arguments
   #VVT: directive2 : arguments

   # Python test code
   def test():
       # Test logic

VVTest Directive DSL
--------------------

The VVTest directive DSL uses comment syntax with specific rules:

Basic Format
~~~~~~~~~~~~

.. code-block:: text

   #VVT: COMMAND ( OPTIONS ) : ARGS

or:

.. code-block:: text

   #VVT: COMMAND ( OPTIONS ) = ARGS

With Test Name
~~~~~~~~~~~~~~

.. code-block:: text

   #VVT: COMMAND (testname="test_name") : arguments

Continuation Lines
~~~~~~~~~~~~~~~~~~

.. code-block:: text

   #VVT: directive_name : argument1
   #VVT:: argument2
   #VVT:: argument3

Parser Behavior
~~~~~~~~~~~~~~~

The ``canary_vvtest`` parser follows these rules:

1. **Line-based**: Each ``#VVT:`` line is a separate directive
2. **Case-sensitive**: Directive names are case-sensitive
3. **Order matters**: Directives are processed in file order
4. **Stop on code**: Parsing stops at first non-comment, non-whitespace line
5. **Error handling**: Parse errors are reported with file and line information

Command Normalization
~~~~~~~~~~~~~~~~~~~~~

Command words are joined with underscores:

- ``depends on`` → ``depends_on``
- ``filter warnings`` → ``filter_warnings``

Option Normalization
~~~~~~~~~~~~~~~~~~~~

Option aliases are normalized:

- ``option`` → ``options``
- ``platform`` → ``platforms``
- ``parameter`` → ``parameters``

Conditional Options
~~~~~~~~~~~~~~~~~~~

Supported conditional/filter options:

- ``testname``
- ``parameters``
- ``options``
- ``platforms``

Argument Syntax
~~~~~~~~~~~~~~~

Arguments begin after ``:`` or ``=``. Non-filter options are passed to the directive-specific handler.

Directive Parsing
-----------------

``canary_vvtest`` parses directives using the following rules:

1. **Line-based**: Each ``#VVT:`` line is a separate directive
2. **Case-sensitive**: Directive names are case-sensitive
3. **Order matters**: Directives are processed in file order
4. **Stop on code**: Parsing stops at first non-comment, non-whitespace line
5. **Error handling**: Parse errors are reported with file and line information

Supported VVTest Directives
---------------------------

The supported directives are documented in two places:

- :doc:`/user/usage.vvtest` gives the user-facing summary for running existing
  VVTest suites under Canary.
- :doc:`vvtest-directives` gives the extension-specific directive reference and
  examples.

This page focuses on the file format and parsing rules rather than restating
every directive description.

Examples
--------

Simple Directive
~~~~~~~~~~~~~~~~

.. code-block:: text

   #VVT: keywords : smoke unit

Directive with Options
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   #VVT: timeout (testname="performance") : 120

Parameterization
~~~~~~~~~~~~~~~~

.. code-block:: text

   #VVT: parameterize : size = 10 20 30

Dependency
~~~~~~~~~~

.. code-block:: text

   #VVT: depends on : setup_test

Copy Directive
~~~~~~~~~~~~~~

.. code-block:: text

   #VVT: copy : input.txt

Link Directive
~~~~~~~~~~~~~~

.. code-block:: text

   #VVT: link : data/

Baseline Directive
~~~~~~~~~~~~~~~~~~

.. code-block:: text

   #VVT: baseline : output.txt

Include Directive
~~~~~~~~~~~~~~~~~

.. code-block:: text

   #VVT: include : common.vvt

Best Practices
--------------

1. **Clear Directives**:
   - Use consistent formatting
   - Group related directives
   - Document complex patterns

2. **Test Name Usage**:
   - Use ``testname`` for multi-test files
   - Keep names descriptive
   - Avoid special characters

3. **Dependency Management**:
   - Explicit dependencies are preferred
   - Use ``depends on`` for workflows
   - Validate dependency graphs

4. **Parameterization**:
   - Use tables for complex parameters
   - Document parameter meanings
   - Test parameter combinations

See Also
--------

- :doc:`vvtest-directives`: Complete directive reference
- :doc:`vvtest-parameterization`: Parameterization details
- :doc:`vvtest-dependencies`: Dependency patterns
