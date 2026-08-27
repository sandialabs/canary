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
=====================

The VVTest directive DSL uses comment syntax with specific rules:

### Basic Format

.. code-block:: text

   #VVT: COMMAND ( OPTIONS ) : ARGS

or:

.. code-block:: text

   #VVT: COMMAND ( OPTIONS ) = ARGS

### With Test Name

.. code-block:: text

   #VVT: COMMAND (testname="test_name") : arguments

### Continuation Lines

.. code-block:: text

   #VVT: directive_name : argument1
   #VVT:: argument2
   #VVT:: argument3

### Parser Behavior

The ``canary_vvtest`` parser follows these rules:

1. **Line-based**: Each ``#VVT:`` line is a separate directive
2. **Case-sensitive**: Directive names are case-sensitive
3. **Order matters**: Directives are processed in file order
4. **Stop on code**: Parsing stops at first non-comment, non-whitespace line
5. **Error handling**: Parse errors are reported with file and line information

### Command Normalization

Command words are joined with underscores:

- ``depends on`` → ``depends_on``
- ``filter warnings`` → ``filter_warnings``

### Option Normalization

Option aliases are normalized:

- ``option`` → ``options``
- ``platform`` → ``platforms``
- ``parameter`` → ``parameters``

### Conditional Options

Supported conditional/filter options:

- ``testname``
- ``parameters``
- ``options``
- ``platforms``

### Argument Syntax

Arguments begin after ``:`` or ``=``. Non-filter options are passed to the directive-specific handler.

Directive Parsing
==================

``canary_vvtest`` parses directives using the following rules:

1. **Line-based**: Each ``#VVT:`` line is a separate directive
2. **Case-sensitive**: Directive names are case-sensitive
3. **Order matters**: Directives are processed in file order
4. **Stop on code**: Parsing stops at first non-comment, non-whitespace line
5. **Error handling**: Parse errors are reported with file and line information

Supported VVTest Directives
---------------------------

Based on ``canary_vvtest/vvt.py`` source, the following directives are supported:

### Core Directives

- **keywords**: Add keywords to the test
- **copy**: Copy files to workspace
- **link**: Create symbolic links
- **sources**: Record source file associations
- **preload**: Preload data or modules
- **parameterize**: Define parameter sets
- **analyze**: Create composite analysis jobs
- **timeout**: Set execution timeout
- **filter_warnings**: Control warning filtering
- **skipif**: Conditionally skip tests
- **baseline**: Declare baseline files
- **enable**: Enable/disable tests
- **name** / **testname**: Set test name
- **depends on** / **depends_on**: Define dependencies

### Special Directives

- **include**: Include another ``.vvt`` file (handled during parsing)
- **insert_directive_file**: Insert directives from another file (handled during parsing)

### Directive Behavior

Each directive is handled by a corresponding method in ``VVTestAdapter``:

- ``f_KEYWORDS``: Add keywords
- ``f_SOURCES``: Handle copy/link/sources
- ``f_PRELOAD``: Set preload
- ``f_PARAMETERIZE``: Parse parameterization
- ``f_ANALYZE``: Set analyze behavior
- ``f_TIMEOUT``: Parse timeout
- ``f_FILTER_WARNINGS``: Set warning filter
- ``f_SKIPIF``: Set skip condition
- ``f_BASELINE``: Parse baseline
- ``f_ENABLE``: Set enable state
- ``f_NAME``: Set test name
- ``f_DEPENDS_ON``: Parse dependencies

Examples
--------

### Simple Directive

.. code-block:: text

   #VVT: keywords : smoke unit

### Directive with Options

.. code-block:: text

   #VVT: timeout (testname="performance") : 120

### Parameterization

.. code-block:: text

   #VVT: parameterize : size = 10 20 30

### Dependency

.. code-block:: text

   #VVT: depends on : setup_test

### Copy Directive

.. code-block:: text

   #VVT: copy : input.txt

### Link Directive

.. code-block:: text

   #VVT: link : data/

### Baseline Directive

.. code-block:: text

   #VVT: baseline : output.txt

### Include Directive

.. code-block:: text

   #VVT: include : common.vvt

Real Supported VVTest Directives
==================================

Based on ``canary_vvtest/vvt.py`` source, the following directives are supported:

### Core Directives

- **keywords**: Add keywords to the test
- **copy**: Copy files to workspace
- **link**: Create symbolic links
- **sources**: Record source file associations
- **preload**: Preload data or modules
- **parameterize**: Define parameter sets
- **analyze**: Create composite analysis jobs
- **timeout**: Set execution timeout
- **filter_warnings**: Control warning filtering
- **skipif**: Conditionally skip tests
- **baseline**: Declare baseline files
- **enable**: Enable/disable tests
- **name** / **testname**: Set test name
- **depends on** / **depends_on**: Define dependencies

### Special Directives

- **include**: Include another ``.vvt`` file (handled during parsing)
- **insert_directive_file**: Insert directives from another file (handled during parsing)

### Directive Behavior

Each directive is handled by a corresponding method in ``VVTestAdapter``:

- ``f_KEYWORDS``: Add keywords
- ``f_SOURCES``: Handle copy/link/sources
- ``f_PRELOAD``: Set preload
- ``f_PARAMETERIZE``: Parse parameterization
- ``f_ANALYZE``: Set analyze behavior
- ``f_TIMEOUT``: Parse timeout
- ``f_FILTER_WARNINGS``: Set warning filter
- ``f_SKIPIF``: Set skip condition
- ``f_BASELINE``: Parse baseline
- ``f_ENABLE``: Set enable state
- ``f_NAME``: Set test name
- ``f_DEPENDS_ON``: Parse dependencies

Examples
-------------

### Empire Example

From ``tests/data/empire.vvt``:

.. code-block:: text

   #VVT: testname = "empire_test"
   #VVT: command = "python empire.py"
   #VVT: timeout = 60
   #VVT: nodes = 1
   #VVT: cpus = 4

### Test Execution Directory

From ``src/canary/examples/vvt/test_exec_dir.vvt``:

.. code-block:: text

   #VVT: testname = "test_exec_dir"
   #VVT: command = "python test.py"
   #VVT: working_dir = "/tmp/test_exec"
   #VVT: timeout = 30

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

- Complete directive reference (see directive documentation)
- Parameterization details (see parameterization section)
- Dependency patterns (see dependencies section)
