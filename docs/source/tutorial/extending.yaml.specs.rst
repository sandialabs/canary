.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-extending-yaml-specs:

Building :class:`~canary.ResolvedSpec` objects
==============================================

A testcase generator ultimately returns runnable work items to ``canary``. In this plugin, those
work items are :class:`~canary.ResolvedSpec` objects.

What the YAML plugin sets
-------------------------

For each test entry, the plugin populates a spec with:

* ``file_root`` and ``file_path``: where the test came from;
* ``family``: the logical test name (the key under ``tests:``);
* ``keywords``: copied from YAML (if present);
* ``attributes``: stores ``description`` under ``attributes["description"]``; and
* ``command``: the concrete command line to execute.

Parameter expansion
-------------------

When a YAML entry provides a ``parameters`` mapping, the plugin computes the Cartesian product of
parameter values and emits one spec per combination:

.. literalinclude:: /static/yaml_generator.py
   :language: python
   :pyobject: YAMLTestGenerator.lock
   :emphasize-lines: 18-33

For each combination, the plugin sets ``spec.parameters`` and expands the script lines using the
parameter values.

Command construction (``sh -c``)
--------------------------------

The plugin runs the YAML script by constructing a shell command:

* it finds a shell with :func:`canary.filesystem.which` (required);
* it passes the script using ``sh -c``; and
* it prefixes the script with ``set -e`` so failures propagate via exit code.

This construction happens in :meth:`~YAMLTestGenerator.lock` when setting ``kwds["command"]``:

.. literalinclude:: /static/yaml_generator.py
   :language: python
   :pyobject: YAMLTestGenerator.lock
   :emphasize-lines: 16, 25, 30

Template substitution
---------------------

When parameters are present, each script line is expanded using :class:`string.Template` and
``safe_substitute``. Placeholders in the YAML should use the ``${name}`` form:

.. code-block:: yaml

   script:
     - echo "a=${a}"

.. note::

   ``safe_substitute`` leaves unknown placeholders unchanged, which can be helpful during
   incremental development of a format. If you prefer strict behavior, use ``substitute`` instead.
