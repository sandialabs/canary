.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Status Determination and Regular Expressions
=============================================

Regular Expression Evaluation Order
-----------------------------------

Regular expression patterns are evaluated in the following order:

1. ``PASS_REGULAR_EXPRESSION`` - Set status to success if matched
2. ``SKIP_RETURN_CODE`` - Set status to skipped if return code matches
3. ``SKIP_REGULAR_EXPRESSION`` - Set status to skipped if matched
4. ``FAIL_REGULAR_EXPRESSION`` - Set status to failed if matched

Evaluation Logic
~~~~~~~~~~~~~~~~

The evaluation follows this precise sequence:

.. code-block:: python

   # Pseudocode showing evaluation order
   if pass_regex_matches:
       status = SUCCESS
   elif return_code == skip_return_code:
       status = SKIPPED
   elif skip_regex_matches:
       status = SKIPPED
   elif fail_regex_matches:
       status = FAILED

Important Notes
~~~~~~~~~~~~~~~

- If both ``PASS_REGULAR_EXPRESSION`` and ``FAIL_REGULAR_EXPRESSION`` match, the test fails since fail patterns are evaluated last.
- Regular expressions are evaluated with ``re.MULTILINE`` flag.
- All patterns in a list are evaluated; the first match determines the outcome.

WILL_FAIL Behavior
------------------

The ``WILL_FAIL`` property inverts the test status logic:

- If the test succeeds but ``WILL_FAIL`` is true, the status becomes ``FAILED``
- If the test fails but ``WILL_FAIL`` is true, the status becomes ``SUCCESS``
- ``SKIPPED`` status is not affected by ``WILL_FAIL``

Example
~~~~~~~

.. code-block:: cmake

   add_test(will_fail_test "false_command")
   set_tests_properties(will_fail_test PROPERTIES WILL_FAIL TRUE)

In this example, even though ``false_command`` fails, the test will be marked as successful because ``WILL_FAIL`` is set to ``TRUE``.

See Also
--------

- :doc:`overview` - Extension overview
- :doc:`ctest-properties` - Supported properties
- :doc:`ctest-example` - Working example