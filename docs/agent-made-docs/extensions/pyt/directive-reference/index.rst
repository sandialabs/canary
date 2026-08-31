.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Directive Reference
===================

Complete reference for all directives in ``canary_pyt.directives``.

.. toctree::
   :maxdepth: 1
   :caption: Directives:

   artifact
   baseline
   copy
   cpus
   depends_on
   enable
   exclusive
   filter_warnings
   aggregate
   gpus
   include
   keywords
   link
   load_module
   nodes
   owners
   parameterize
   preload
   set_attribute
   set_id
   skipif
   source
   sources
   stages
   testname
   timeout
   xdiff
   xfail

Overview
--------

This section documents all directives available in ``canary_pyt.directives``.

Each directive has its own page with:

- **Signature**: Function signature
- **Purpose**: What the directive does
- **Parameters**: Detailed parameter descriptions
- **Effect**: How it affects generated jobs
- **When**: Whether it affects discovery/generation or runtime
- **Conditional Activation**: Support for ``when`` parameter
- **Examples**: Usage examples
- **Edge Cases**: Special considerations
- **Notes**: Additional information

Directive Index
---------------

**Metadata and Classification**

.. hlist::
   :columns: 2

   - :doc:`artifact`
   - :doc:`baseline`
   - :doc:`keywords`
   - :doc:`owners`
   - :doc:`set_id`
   - :doc:`sources`
   - :doc:`stages`
   - :doc:`testname`

**Parameterization**

.. hlist::
   :columns: 2

   - :doc:`cpus`
   - :doc:`gpus`
   - :doc:`nodes`
   - :doc:`parameterize`

**Dependencies**

.. hlist::
   :columns: 1

   - :doc:`depends_on`

**Resources**

.. hlist::
   :columns: 2

   - :doc:`cpus`
   - :doc:`exclusive`
   - :doc:`gpus`
   - :doc:`nodes`

**Assets and Files**

.. hlist::
   :columns: 2

   - :doc:`artifact`
   - :doc:`baseline`
   - :doc:`copy`
   - :doc:`link`
   - :doc:`sources`

**Execution Control**

.. hlist::
   :columns: 2

   - :doc:`enable`
   - :doc:`skipif`
   - :doc:`timeout`
   - :doc:`xfail`
   - :doc:`xdiff`

**Advanced**

.. hlist::
   :columns: 2

   - :doc:`filter_warnings`
   - :doc:`aggregate`
   - :doc:`include`
   - :doc:`load_module`
   - :doc:`preload`
   - :doc:`set_attribute`
   - :doc:`source`

Usage Notes
-----------

**Importing Directives**:

.. code-block:: python

   import canary_pyt

   # Use fully qualified name
   canary_pyt.directives.keywords("smoke")

**Conditional Activation**:

Most directives support the ``when`` parameter:

.. code-block:: python

   canary_pyt.directives.keywords("extended", when="-o extended")

See :doc:`../conditional-activation` for details.

**Directive Recording**:

Directives are recorded during the discovery phase. They must appear at module level, not inside functions or classes.

Aliases
-------

Some directives have aliases for compatibility or convenience:

**analyze**
   Alias for :doc:`aggregate`. Legacy name for composite analysis.

**generate_composite_base_case**
   Alias for :doc:`aggregate`. Legacy name for composite analysis.

**name**
   Alias for :doc:`testname`. Sets the test name.

**owner**
   Alias for :doc:`owners`. Specifies test owners.

These aliases are documented on their primary directive pages.

See Also
--------

- :doc:`../directives`: Directives overview
- :doc:`../file-structure`: File organization
- :doc:`../conditional-activation`: When expressions
