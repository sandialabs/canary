.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

How does canary work?
=====================

Given path on your filesystem, ``canary``

* searches for **test files**;
* generates **test cases** from those test files;
* asynchronously executes the test cases; and
* reports the results of the execution.

``canary`` has many other capabilities designed to streamline the testing process.
