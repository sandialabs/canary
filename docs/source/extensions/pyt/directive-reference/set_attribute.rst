.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

set_attribute
=============

.. currentmodule:: canary_pyt.directives

.. autofunction:: set_attribute

Purpose
-------

Set arbitrary custom attributes on the job. Attributes are used to store additional metadata and custom properties.

Parameters
----------

:param when: Optional conditional activation (WhenType)
:param \*\*attributes: Custom attribute key-value pairs

Effect on Generated Jobs
------------------------

- Adds custom attributes to job
- Attributes are stored in job metadata
- Accessible via ``instance.attributes`` at runtime
- Used for custom metadata and properties

When
----

- **Affects**: Generation phase
- **Runtime**: Attributes accessible via instance

Conditional Activation
----------------------

Supports ``when`` parameter for conditional activation:

.. code-block:: python

   canary_pyt.directives.set_attribute(
       priority="high",
       when="-o important"
   )

Examples
--------

**Single Attribute**:

.. code-block:: python

   canary_pyt.directives.set_attribute(priority="high")

**Multiple Attributes**:

.. code-block:: python

   canary_pyt.directives.set_attribute(
       priority="high",
       category="performance",
       timeout_factor=2.0
   )

**Conditional Attributes**:

.. code-block:: python

   canary_pyt.directives.set_attribute(
       important=True,
       when="keywords=critical"
   )

Edge Cases
----------

**Empty Attributes**:

.. code-block:: python

   canary_pyt.directives.set_attribute()  # No attributes set

**Invalid Keys**:

.. code-block:: python

   canary_pyt.directives.set_attribute("invalid-key"=1)  # Error

Notes
-----

- Attributes are custom key-value pairs
- Values must be JSON-serializable
- Attributes are stored in job metadata
- Access attributes at runtime via ``instance.attributes``
- Use for custom properties and metadata

Runtime Access
--------------

.. code-block:: python

   def main():
       instance = canary.get_instance()
       priority = instance.attributes.get("priority", "normal")
       print(f"Priority: {priority}")

Best Practices
--------------

1. **Metadata**:

   .. code-block:: python

      canary_pyt.directives.set_attribute(
          author="alice",
          review_date="2024-01-01"
      )

2. **Custom Properties**:

   .. code-block:: python

      canary_pyt.directives.set_attribute(
          test_type="regression",
          coverage_target="95%"
      )

3. **Conditional**:

   .. code-block:: python

      canary_pyt.directives.set_attribute(
          priority="high",
          when="-o important"
      )

See Also
--------

- :doc:`set_id`: Set ID directive
- :doc:`keywords`: Keywords directive
- :doc:`../test-instance`: Test instance access
