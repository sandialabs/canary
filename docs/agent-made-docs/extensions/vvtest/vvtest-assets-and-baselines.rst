.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

VVTest Assets and Baselines
===========================

Assets are files needed by tests, while baselines are reference files used for comparison. Both are managed by ``canary_vvtest`` directives.

copy Directive
--------------

Copy files to the workspace:

.. code-block:: text

   #VVT: copy : file1.txt file2.txt
   #VVT: copy : inputs/*.dat

### Behavior

- Files copied from source tree to workspace
- Supports glob patterns
- Files are read-only in workspace

### rename Option

Rename files during copy:

.. code-block:: text

   #VVT: copy (rename) : old.txt new.txt

Requires ``src,dst`` pairs.

link Directive
--------------

Create symbolic links:

.. code-block:: text

   #VVT: link : directory/
   #VVT: link : data.txt

### Behavior

- Creates symlinks from source tree
- Changes to linked files affect source
- Uses less disk space than copying

sources Directive
-----------------

Record source file associations:

.. code-block:: text

   #VVT: sources : input.csv

### Behavior

- Records files in job metadata
- Files are not automatically copied or linked
- Used for tracking dependencies

### Action Mapping

- ``copy`` → ``copy`` action
- ``link`` → ``link`` action
- ``sources`` → ``none`` action

baseline Directive
------------------

Declare baseline files for comparison:

.. code-block:: text

   #VVT: baseline : output.txt
   #VVT: baseline : --flag results.txt

### Flag-Based Baseline

Arguments starting with ``--`` become flags:

.. code-block:: text

   #VVT: baseline : --baseline output.txt

### Copy-Based Baseline

``src,dst`` pairs for file copying:

.. code-block:: text

   #VVT: baseline : expected.txt actual.txt

### Parse Errors

Malformed baseline entries raise parse errors.

Examples
--------

### Copy Files

.. code-block:: text

   #VVT: copy : test_data.csv config.json

### Link Directory

.. code-block:: text

   #VVT: link : reference_data/

### Record Sources

.. code-block:: text

   #VVT: sources : input.csv

### Baseline Comparison

.. code-block:: text

   #VVT: baseline : expected_output.txt

### Rename Files

.. code-block:: text

   #VVT: copy (rename) : old.txt new.txt

Best Practices
--------------

1. **Copy for Isolation**:

   .. code-block:: text

      #VVT: copy : test_data.csv

2. **Link for Large Files**:

   .. code-block:: text

      #VVT: link : large_dataset.dat

3. **Record for Provenance**:

   .. code-block:: text

      #VVT: sources : input.csv

4. **Baseline for Regression**:

   .. code-block:: text

      #VVT: baseline : expected_output.txt

See Also
--------

- :doc:`vvtest-directives`: Complete directive reference
- :doc:`file-format`: File format details
