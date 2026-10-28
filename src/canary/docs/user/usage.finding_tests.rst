.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-finding:

Finding and listing test files
==============================

``canary find`` scans pathspecs, applies the same selection filters used by
``canary run``, and prints the matching specs in one of several output formats.

Use it when you want to inspect what Canary would discover before creating a
selection or starting a run.


Basic usage
-----------

Prefer positional pathspecs in examples:

.. code-block:: console

   canary find PATHSPEC

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}]
   :script: [{"args": "canary find .", "cwd": "examples"}]

Alternative output modes
------------------------

``canary find`` supports several output modes beyond the default spec listing:

.. code-block:: console

   canary find --paths .
   canary find --files .
   canary find --keywords .
   canary find --lock .

These modes are useful when you want to:

- see file paths grouped by root with ``--paths``
- print only the discovered file paths with ``--files``
- inspect available keywords with ``--keywords``
- export the resolved specs to ``testspecs.lock`` with ``--lock``


Filter by keyword
-----------------

The ``-k`` option will filter tests by keyword.  Eg., find tests with the ``basic`` keyword:

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}]
   :script: [{"args": "canary find -k basic .", "cwd": "examples"}]

The ``-k`` option can take a python expression, eg

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}]
   :script: [{"args": "canary find -k 'basic and second' .", "cwd": "examples"}]


Print a test DAG
----------------

The ``-g`` option will print a graph of test dependencies:

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}]
   :script: [{"args": "canary find -g .", "cwd": "examples"}]


Show available keywords
-----------------------

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}]
   :script: [{"args": "canary find --keywords .", "cwd": "examples"}]

See also
--------

- :doc:`/user/usage.select` for saving a filtered set of specs as a reusable tag
- :doc:`/user/usage.run` for executing the selected specs
