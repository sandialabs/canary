Status and Regex Behavior
=========================

When running CTest tests, Canary determines the final job status by evaluating the output and return code against several properties.

Evaluation Order
-----------------

The status is evaluated in the following order of precedence:

1.  **Pass Regular Expression**: If PASS_REGULAR_EXPRESSION is defined and any pattern matches the output, the status is set to SUCCESS.
2.  **Skip Return Code**: If SKIP_RETURN_CODE is defined and the return code matches, the status is set to SKIPPED.
3.  **Skip Regular Expression**: If SKIP_REGULAR_EXPRESSION is defined and any pattern matches, the status is set to SKIPPED.
4.  **Fail Regular Expression**: If FAIL_REGULAR_EXPRESSION is defined and any pattern matches, the status is set to FAILED.
5.  **Will Fail**: If WILL_FAIL is true:
    *   A successful return code results in FAILED.
    *   A failed return code results in SUCCESS.

Common Pitfalls
---------------

**Conflicting Regexes**: If a test defines both a pass and a fail regular expression, and the output contains both, the **fail regular expression takes precedence** if the pass regex was not already matched (though the order listed above shows Pass is checked first). 

*Correction based on source*: Looking at , the order is:
1. Pass Regex $\rightarrow$ SUCCESS (break)
2. Skip Return Code $\rightarrow$ SKIPPED
3. Skip Regex $\rightarrow$ SKIPPED (break)
4. Fail Regex $\rightarrow$ FAILED

If a match is found in the Pass Regex, the test is immediately marked success. Otherwise, it checks for skips, then finally for failures.
