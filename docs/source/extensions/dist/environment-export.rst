.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Environment Export
==================

The ``canary_dist`` extension provides controlled environment variable propagation to remote execution hosts. This feature enables users to specify which environment variables from the submission environment should be available during remote test execution.

Environment Export Overview
---------------------------

By default, **no environment variables** are propagated to remote hosts. This conservative approach prevents unintended environment leakage and ensures reproducible execution.

Export Mechanisms
-----------------

The ``--export`` option (or ``-E``) controls environment variable propagation:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 -E <variables>|ALL ./tests

Export Modes
------------

Default Mode (No Export)
~~~~~~~~~~~~~~~~~~~~~~~~

**Behavior**: No environment variables are propagated

**Command**: (no ``-E`` option specified)

**Use Case**: Maximum reproducibility, minimal environment influence

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 ./tests

ALL Mode
~~~~~~~~~

**Behavior**: All environment variables are propagated

**Command**: ``--export=ALL``

**Use Case**: Full environment replication, maximum compatibility

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --export=ALL ./tests

Selective Mode
~~~~~~~~~~~~~~

**Behavior**: Specific variables are exported

**Command**: ``--export=VAR1,VAR2,VAR3=value``

**Use Case**: Controlled environment propagation, balance between reproducibility and necessity

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --export=MYVAR,OTHER ./tests

Export Syntax
-------------

Variable Name Export
~~~~~~~~~~~~~~~~~~~~

Export variables by name to propagate current values:

.. code-block:: console

   --export=MYVAR
   --export=VAR1,VAR2,VAR3

This exports the current values of the specified variables.

Variable with Value Export
~~~~~~~~~~~~~~~~~~~~~~~~~~

Export variables with specific values:

.. code-block:: console

   --export=MYVAR=value
   --export=VAR1=value1,VAR2=value2

This sets the specified variables to the given values on the remote host.

Mixed Export
~~~~~~~~~~~~

Combine variable name and value exports:

.. code-block:: console

   --export=MYVAR,OTHER=specific_value,ANOTHER

This exports ``MYVAR`` and ``ANOTHER`` with their current values, and ``OTHER`` with the value ``"specific_value"``.

Special Variable Handling
-------------------------

LOADEDMODULES Variable
~~~~~~~~~~~~~~~~~~~~~~

The ``LOADEDMODULES`` variable receives special handling:

**Behavior**: If exported, the modules are loaded on the remote host

**Effect**: Module environment is reconstructed on remote host

**Example**:

.. code-block:: console

   --export=LOADEDMODULES

This ensures that any modules loaded in the submission environment are also loaded on the remote host.

Environment Export Process
---------------------------

The environment export process involves:

1. **Variable Collection**: Gather variables to export based on ``--export`` option
2. **Variable Processing**: Process variable names and values
3. **Environment Construction**: Build remote execution environment
4. **Environment Propagation**: Transfer environment to remote host
5. **Environment Application**: Apply environment on remote host

Export Examples
---------------

Basic Variable Export
~~~~~~~~~~~~~~~~~~~~~

Export specific variables by name:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --export=PATH,HOME ./tests

Variable with Value Export
~~~~~~~~~~~~~~~~~~~~~~~~~~

Export variables with specific values:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --export=DEBUG=1,VERBOSE=true ./tests

Mixed Export
~~~~~~~~~~~~

Combine different export styles:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --export=PATH,DEBUG=1,LOADEDMODULES ./tests

Module Environment Export
~~~~~~~~~~~~~~~~~~~~~~~~~

Export module environment:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --export=LOADEDMODULES ./tests

All Environment Export
~~~~~~~~~~~~~~~~~~~~~~

Export entire environment:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --export=ALL ./tests

Environment Export Considerations
----------------------------------

Security Considerations
~~~~~~~~~~~~~~~~~~~~~~~

- **Sensitive Data**: Avoid exporting variables containing credentials or sensitive information
- **Environment Pollution**: Excessive export can pollute remote environment
- **Reproducibility**: Environment export can reduce test reproducibility

Performance Considerations
~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Transfer Overhead**: Large environment variables increase transfer time
- **Processing Cost**: Environment processing adds to submission overhead
- **Memory Usage**: Large environments consume more memory on remote hosts

Compatibility Considerations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Platform Differences**: Environment variables may behave differently across platforms
- **Shell Differences**: Variable expansion and handling may differ
- **Module Systems**: Module environment reconstruction may have limitations

Best Practices
--------------

Minimal Export Principle
~~~~~~~~~~~~~~~~~~~~~~~~

Export only the variables necessary for test execution:

.. code-block:: console

   # Good: Minimal necessary export
   --export=REQUIRED_VAR

   # Avoid: Unnecessary broad export
   --export=ALL

Explicit Value Export
~~~~~~~~~~~~~~~~~~~~~

Prefer explicit values for critical variables:

.. code-block:: console

   # Good: Explicit value ensures consistency
   --export=DEBUG=1

   # Risky: Current value may vary
   --export=DEBUG

Module Environment Control
~~~~~~~~~~~~~~~~~~~~~~~~~~

Use module export judiciously:

.. code-block:: text

   # Good: When modules are truly needed
   --export=LOADEDMODULES

   # Avoid: When modules aren't necessary
   --export=ALL

Environment Validation
-----------------------

Validate environment export behavior:

.. code-block:: console

   # Check what variables would be exported
   env | grep -E "(VAR1|VAR2)"

   # Test with minimal export first
   python3 -m canary dist run --server-url http://pool.example:8000 --export=MINIMAL ./tests

   # Gradually add necessary variables
   python3 -m canary dist run --server-url http://pool.example:8000 --export=MINIMAL,ADDITIONAL ./tests

Environment Export Errors
--------------------------

Common environment export issues:

Missing Variables
~~~~~~~~~~~~~~~~~

**Symptoms**: Tests fail due to missing environment variables

**Solutions**:

- Identify required variables
- Add variables to export list
- Consider using explicit values

Variable Conflicts
~~~~~~~~~~~~~~~~~~

**Symptoms**: Variable conflicts between submission and remote environments

**Solutions**:

- Use explicit values to resolve conflicts
- Review variable precedence rules
- Test environment compatibility

Module Loading Failures
~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**: Module loading errors on remote host

**Solutions**:

- Verify module availability on remote hosts
- Check module environment compatibility
- Review module dependency requirements

Environment Size Issues
~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**: Large environment variables causing transfer issues

**Solutions**:

- Reduce environment size
- Use selective export instead of ALL
- Consider environment compression

Debugging Environment Export
-----------------------------

Debug environment export issues:

.. code-block:: console

   # Check current environment
   env

   # Test with verbose logging
   python3 -m canary dist run --server-url http://pool.example:8000 --export=DEBUG --verbose ./tests

   # Check specific variable values
   echo $VARIABLE_NAME

   # Test remote environment
   ssh remote-host env

Environment Export and Reproducibility
----------------------------------------

Environment export affects test reproducibility:

- **No Export**: Maximum reproducibility
- **Selective Export**: Balanced reproducibility
- **ALL Export**: Minimum reproducibility

Consider reproducibility requirements when choosing export mode.

Environment Export in CI/CD
----------------------------

In CI/CD environments:

- Use explicit values for critical variables
- Minimize environment export for reproducibility
- Document required environment variables
- Validate environment compatibility across platforms

Environment Export Limitations
-------------------------------

The environment export feature has several limitations:

- No automatic environment detection
- Limited module system support
- No environment validation
- Platform-specific behavior differences
- No environment variable transformation

These limitations should be considered when designing test environments.
