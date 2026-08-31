.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

keywords
========

.. currentmodule:: canary_pyt.directives

.. autofunction:: keywords

Purpose
-------

Classify tests with keywords for selection and filtering. Keywords enable test categorization and selective execution.

Parameters
----------

:param \*args: Keyword strings
:param when: Optional conditional activation (WhenType)

Effect on Generated Jobs
------------------------

- Adds keywords to job metadata
- Keywords are used for test selection with ``-k`` option
- Keywords are accessible via ``instance.keywords`` at runtime
- Multiple calls accumulate keywords

When
----

- **Affects**: Generation phase
- **Runtime**: Keywords accessible via ``canary.get_instance().keywords``

Conditional Activation
----------------------

Supports ``when`` parameter for conditional activation:

.. code-block:: python

   canary_pyt.directives.keywords(
       "extended",
       when="-o extended"
   )

Examples
--------

**Single Keyword**:

.. code-block:: python

   canary_pyt.directives.keywords("smoke")

**Multiple Keywords**:

.. code-block:: python

   canary_pyt.directives.keywords("smoke", "unit", "fast")

**Multiple Calls**:

.. code-block:: python

   canary_pyt.directives.keywords("smoke")
   canary_pyt.directives.keywords("unit")
   # Results in: ["smoke", "unit"]

**Conditional Keywords**:

.. code-block:: python

   canary_pyt.directives.keywords("extended", when="-o extended")

**Platform-Specific Keywords**:

.. code-block:: python

   canary_pyt.directives.keywords("linux", when="platform=linux")
   canary_pyt.directives.keywords("windows", when="platform=windows")

Edge Cases
----------

**Empty Keywords**:

.. code-block:: python

   canary_pyt.directives.keywords()  # No keywords added

**Duplicate Keywords**:

.. code-block:: python

   canary_pyt.directives.keywords("smoke", "smoke")  # Duplicate "smoke"

**Special Characters**:

.. code-block:: python

   canary_pyt.directives.keywords("test-group")  # OK
   canary_pyt.directives.keywords("test group")  # OK (spaces allowed)

Notes
-----

- Keywords are case-sensitive
- Keywords can contain letters, numbers, underscores, hyphens, and spaces
- Avoid very long keyword lists (impacts performance)
- Keywords are inherited by dependent jobs

Runtime Access
--------------

.. code-block:: python

   def main():
       instance = canary.get_instance()
       if "smoke" in instance.keywords:
           print("Running smoke test")
       if "extended" in instance.keywords:
           print("Running extended test")

Command-Line Selection
----------------------

Select tests by keyword:

.. code-block:: console

   # Run tests with "smoke" keyword
   python3 -m canary run -k smoke tests/

   # Run tests with "smoke" OR "unit" keywords
   python3 -m canary run -k "smoke or unit" tests/

   # Run tests with "smoke" AND "fast" keywords
   python3 -m canary run -k "smoke and fast" tests/

   # Exclude tests with "slow" keyword
   python3 -m canary run -k "not slow" tests/

See Also
--------

- :doc:`../conditional-activation`: Conditional activation overview
- :doc:`enable`: Enable/disable tests
- :doc:`skipif`: Conditionally skip tests
