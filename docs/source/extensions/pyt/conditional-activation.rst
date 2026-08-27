.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Conditional Activation
======================

Conditional activation controls when directives apply using ``when`` expressions. This enables selective test execution based on options, keywords, parameters, and platform.

when Parameter
--------------

Most directives support the ``when`` parameter:

.. code-block:: python

   canary_pyt.directives.keywords("extended", when="-o extended")

String Form
-----------

Simple string conditions:

.. code-block:: python

   canary_pyt.directives.keywords("smoke", when="-o smoke")

Dict Form
---------

Dictionary conditions for complex logic:

.. code-block:: python

   canary_pyt.directives.keywords(
       "extended",
       when={"options": "extended", "platform": "linux"}
   )

Options
-------

Activate based on command-line options:

.. code-block:: python

   canary_pyt.directives.enable(True, when="-o extended")

**Behavior**:

- ``-o extended``: Directive applies
- No ``-o extended``: Directive does not apply

Keywords
--------

Activate based on keywords:

.. code-block:: python

   canary_pyt.directives.timeout(120, when="keywords=extended")

**Behavior**:

- ``-k extended``: Directive applies
- No ``extended`` keyword: Directive does not apply

Parameters
----------

Activate based on parameter values:

.. code-block:: python

   canary_pyt.directives.keywords(
       "large",
       when="parameters[size]=large"
   )

**Behavior**:

- ``size=large``: Directive applies
- Other sizes: Directive does not apply

Test Name
---------

Activate based on test name:

.. code-block:: python

   canary_pyt.directives.timeout(60, when="testname=performance")

**Behavior**:

- Test name matches ``performance``: Directive applies
- Other names: Directive does not apply

Platforms
----------

Activate based on platform:

.. code-block:: python

   canary_pyt.directives.skipif(
       True,
       reason="Windows not supported",
       when="platform=windows"
   )

**Platform Sources**:

- ``sys.platform``: ``linux``, ``win32``, ``darwin``, etc.
- Environment variables: ``PLATFORM``, ``OS``, etc.

Examples
--------

**Command-Line Option**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.keywords("extended", when="-o extended")

**Keyword Activation**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.timeout(120, when="keywords=performance")

**Parameter Activation**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.parameterize("size", ["small", "large"])
   canary_pyt.directives.cpus(8, when="parameters[size]=large")

**Platform Activation**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.skipif(
       True,
       reason="Windows not supported",
       when="platform=windows"
   )

**Multiple Conditions**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.keywords(
       "extended",
       when="-o extended and keywords=performance"
   )

Interaction with -o Options
---------------------------

Command-line options override defaults:

.. code-block:: console

   # Run with extended option
   python3 -m canary run -o extended tests/

.. code-block:: python

   canary_pyt.directives.keywords("extended", when="-o extended")

**Behavior**:

- With ``-o extended``: ``extended`` keyword added
- Without ``-o extended``: ``extended`` keyword not added

Complex Conditions
------------------

Combine conditions with ``and``, ``or``:

.. code-block:: python

   canary_pyt.directives.keywords(
       "special",
       when="-o extended and platform=linux"
   )

**Operators**:

- ``and``: Both conditions must be true
- ``or``: Either condition can be true
- ``not``: Condition must be false

Negation
--------

Negate conditions:

.. code-block:: python

   canary_pyt.directives.skipif(
       True,
       reason="Not needed",
       when="not -o quick"
   )

**Behavior**:

- Without ``-o quick``: Test skipped
- With ``-o quick``: Test runs

Runtime Access
--------------

Access conditional activation at runtime:

.. code-block:: python

   def main():
       instance = canary.get_instance()
       if "extended" in instance.keywords:
           # Extended test logic

Best Practices
--------------

1. **Descriptive Conditions**:

   .. code-block:: python

      canary_pyt.directives.keywords(
          "performance",
          when="-o performance"
      )

2. **Platform-Specific**:

   .. code-block:: python

      canary_pyt.directives.skipif(
          True,
          reason="Linux only",
          when="platform!=linux"
      )

3. **Parameter-Based**:

   .. code-block:: python

      canary_pyt.directives.cpus(
          8,
          when="parameters[size]=large"
      )

4. **Conditional Resources**:

   .. code-block:: python

      canary_pyt.directives.timeout(
          120,
          when="keywords=extended"
      )

See Also
--------

- :doc:`directive-reference/keywords`: Keywords directive
- :doc:`directive-reference/enable`: Enable directive
- :doc:`directive-reference/skipif`: Skipif directive
- :doc:`directive-reference/parameterize`: Parameterization directive
