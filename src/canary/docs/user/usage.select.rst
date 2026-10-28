.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-select:

Creating and managing tagged selections
=======================================

Canary now has two related selection workflows:

- ``canary selection create`` discovers specs from filesystem pathspecs and saves them under a tag.
- ``canary select`` filters specs that are already collected in the workspace and saves the filtered result under a tag.

In practice, ``canary selection create`` is the newer discovery-oriented entry point,
while ``canary select`` remains useful when you want to build a tag from specs that
already exist in the workspace.

Use this page for the main workflows. For the complete command reference, see
:ref:`canary select <canary-select>` and ``canary selection create -h``.

When to use ``select``
----------------------

Use these commands when you want to:

- save a filtered subset of specs under a stable name
- rerun the same subset repeatedly with ``canary run TAG``
- create one selection from another using additional filters
- rename or delete an existing selection

``canary selection create`` works directly from filesystem pathspecs. A common
flow is:

1. create a selection from one or more pathspecs with ``canary selection create``
2. optionally refine an existing workspace selection with ``canary select``
3. run it with ``canary run TAG``

Create a selection from pathspecs
---------------------------------

``canary selection create`` accepts the same pathspec syntax as ``canary run``,
``canary find``, and ``canary collect``:

.. code-block:: console

   canary selection create basic ./basic
   canary selection create smoke ./tests/smoke
   canary selection create focused .:basic/first/first.pyt

This command discovers specs from the given paths, applies any requested
filters, and stores the result in the workspace under the given tag.

Create a basic selection from collected specs
---------------------------------------------

If specs are already collected into the workspace, create a tag with:

.. code-block:: console

   canary collect -r ./basic
   canary select basic

Then run it later with:

.. code-block:: console

   canary run basic

Create a filtered selection
---------------------------

Both ``canary selection create`` and ``canary select`` use the same core
selection filters as ``canary run`` and ``canary find``:

.. code-block:: console

   canary selection create fast ./tests -k fast
   canary selection create gpu-tests ./tests -p gpus>0

   canary select fast -k fast
   canary select nightly --owner team-a
   canary select gpu-tests -p gpus>0
   canary select io-regex --regex "restart|checkpoint"

This makes selections useful as named, repeatable views over a larger collected
spec set.

Restrict by source root
-----------------------

Use ``--from-root`` with ``canary select`` when the workspace contains collected specs from multiple
source trees and you want a tag built only from one or more roots:

.. code-block:: console

   canary select unit --from-root ./tests/unit
   canary select integration --from-root ./tests/integration

Build one selection from another
--------------------------------

Use ``--from`` to derive a new tag from an existing selection instead of from
the full collected spec set:

.. code-block:: console

   canary select nightly
   canary select nightly-failed --from nightly -k failed

This is useful when you want layered selections without recollecting specs.

Rename or delete a selection
----------------------------

Selections can be renamed or removed directly:

.. code-block:: console

   canary select renamed-tag --move old-tag
   canary select obsolete-tag --delete

How ``selection create`` and ``select`` differ from ``find`` and ``run``
------------------------------------------------------------------------

- Use ``canary find`` to inspect what Canary would discover and how filters affect the result.
- Use ``canary selection create`` to save a reusable tag directly from filesystem pathspecs.
- Use ``canary select`` to save a reusable tag from specs that are already collected in the workspace.
- Use ``canary run`` to execute a selection immediately.

See also
--------

- :doc:`/user/usage.finding_tests` for discovery and inspection workflows
- :doc:`/user/usage.run` for executing a saved selection
- :doc:`/user/basics.workspace` for how selections fit into workspace state
