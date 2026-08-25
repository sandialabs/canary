.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Directives Overview
===================

Directives are the primary interface for defining test behavior in `.pyt` files. They are Python functions in the ``canary_pyt.directives`` namespace that record test metadata, requirements, and configuration.

Directive Categories
--------------------

Directives are organized by function:

**Metadata and Classification**
   - ``keywords``: Classify tests
   - ``testname``: Set test name
   - ``owners``: Specify test owners
   - ``set_id``: Set explicit test ID

**Parameterization**
   - ``parameterize``: Define parameter sets
   - ``cpus``: Set CPU requirements
   - ``gpus``: Set GPU requirements
   - ``nodes``: Set node requirements

**Dependencies**
   - ``depends_on``: Define job dependencies

**Resources**
   - ``cpus``: Fixed CPU count
   - ``gpus``: Fixed GPU count
   - ``nodes``: Fixed node count
   - ``exclusive``: Exclusive resource access

**Assets and Files**
   - ``copy``: Copy files to workspace
   - ``link``: Link files to workspace
   - ``sources``: Declare source files
   - ``artifact``: Declare expected artifacts
   - ``baseline``: Declare baseline files

**Execution Control**
   - ``timeout``: Set execution timeout
   - ``enable``: Enable/disable tests
   - ``skipif``: Conditionally skip tests
   - ``xfail``: Mark expected failures
   - ``xdiff``: Mark expected differences

**Conditional Activation**
   - ``when`` parameter: Conditional activation

**Advanced**
   - ``aggregate``: Composite analysis
   - ``set_attribute``: Custom attributes
   - ``load_module``: Load environment modules
   - ``preload``: Preload data
   - ``include``: Include other files
   - ``filter_warnings``: Control warnings

Directive Signature Pattern
---------------------------

Most directives follow this pattern:

.. code-block:: python

   def directive_name(
       arg1: Type1,
       arg2: Type2 | None = None,
       *,
       when: WhenType | None = None
   ) -> None:
       """Directive documentation."""
       pass

Where:

- Positional arguments define primary behavior
- ``when`` parameter enables conditional activation
- Return type is always ``None`` (directives record, don't return)

Using Directives
----------------

**Basic Usage**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.keywords("smoke", "unit")
   canary_pyt.directives.timeout(60)

**With Conditional Activation**:

.. code-block:: python

   canary_pyt.directives.keywords("extended", when="-o extended")
   canary_pyt.directives.timeout(120, when="keywords=extended")

**Multiple Calls**:

.. code-block:: python

   canary_pyt.directives.keywords("smoke")
   canary_pyt.directives.keywords("unit")
   # Results in: keywords = ["smoke", "unit"]

Directive Reference
-------------------

Complete directive reference is available in :doc:`directive-reference/index`.

Each directive has its own dedicated page with detailed information including:

- Signature (using ``autofunction``)
- Purpose and use cases
- Parameters and options
- Effect on generated jobs
- When it is evaluated
- Conditional activation support
- Multiple examples
- Edge cases and diagnostics
- Cross-references to related directives

For the full list of directives and their documentation, see :doc:`directive-reference/index`.

- Signature
- Purpose
- Parameters
- Effect on generated jobs
- Examples
- Edge cases
- Notes

Important Directives
--------------------

These directives are central to `.pyt` authoring:

**parameterize**
   Define parameter sets for test variants. See :doc:`parameterization`.

**depends_on**
   Define dependencies between jobs. See :doc:`dependencies`.

**timeout**
   Set execution timeout. See :doc:`expected-results`.

**keywords**
   Classify tests for selection. See :doc:`conditional-activation`.

**cpus, gpus, nodes**
   Set resource requirements. See :doc:`resources`.

**copy, link, artifact, baseline**
   Manage files and expected outputs. See :doc:`assets`, :doc:`artifacts`, :doc:`baselines`.

**aggregate**
   Create composite analysis jobs. See :doc:`composite-analysis`.

Directive Discovery
-------------------

Directives are discovered during the discovery phase:

1. Canary scans for `.pyt` files
2. ``PYTLoader`` executes the file
3. Directives are monkeypatched to ``DirectiveRecorder``
4. Calls are recorded with file and line information

**Not Discovered**:

- Directives inside functions or classes
- Directives executed after ``if __name__ == "__main__"``
- Directives in imported modules (unless those modules are also scanned)

Directive Precedence
--------------------

When multiple directives affect the same property:

1. **Accumulating Directives** (e.g., ``keywords``):
   - Multiple calls accumulate values
   - Order matters for list construction

2. **Replacing Directives** (e.g., ``timeout``):
   - Last call wins
   - Previous values are replaced

3. **Conditional Directives**:
   - Non-conditional directives apply first
   - Conditional directives apply only when condition is met
   - Conditions are evaluated at generation time

Best Practices
--------------

1. **Use Canonical Namespace**:

   .. code-block:: python

      import canary_pyt
      canary_pyt.directives.keywords("smoke")

   Avoid deprecated ``canary.directives``.

2. **Place at Module Level**:

   .. code-block:: python

      # GOOD - at module level
      canary_pyt.directives.timeout(60)

      def test():
          pass

3. **Group Related Directives**:

   .. code-block:: python

      # Resource directives
      canary_pyt.directives.cpus(4)
      canary_pyt.directives.gpus(1)

      # Parameterization
      canary_pyt.directives.parameterize("size", [10, 20])

4. **Use Conditional Activation**:

   .. code-block:: python

      canary_pyt.directives.keywords("extended", when="-o extended")

5. **Document Complex Directives**:

   .. code-block:: python

      # Complex parameterization for performance testing
      canary_pyt.directives.parameterize(
          "workload",
          ["small", "medium", "large"],
          when="keywords=performance"
      )

Common Pitfalls
---------------

**Avoid**:

.. code-block:: python

   # BAD - inside function
   def test():
       canary_pyt.directives.timeout(60)  # Not recorded!

   # BAD - after runtime guard
   if __name__ == "__main__":
       canary_pyt.directives.keywords("smoke")  # Not recorded!

   # BAD - deprecated namespace
   import canary
   canary.directives.keywords("smoke")  # Use canary_pyt.directives instead

See Also
--------

- :doc:`directive-reference/index`: Complete directive reference
- :doc:`file-structure`: File organization
- :doc:`patterns`: Common directive patterns
- :doc:`limitations`: Directive limitations
