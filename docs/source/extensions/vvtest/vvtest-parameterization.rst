.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

VVTest Parameterization
=======================

Parameterization enables test variant generation in VVTest files. The ``parameterize`` directive defines parameter sets that create multiple test instances.

Ordinary Parameterization
-------------------------

### Syntax

.. code-block:: text

   #VVT: parameterize : name = value1 value2 value3
   #VVT: parameterize (type=int) : size = 10 20 30

### Table Parsing

Arguments are parsed as a table:

- **Columns**: Comma-separated
- **Rows**: Whitespace-separated
- **Result**: List of parameter dictionaries

**Example**:

.. code-block:: text

   #VVT: parameterize : size,mode = 10,fast 20,slow

Generates 2 parameter sets:
- ``size=10, mode=fast``
- ``size=20, mode=slow``

### Scalar Casting

The ``scalar.cast`` function handles type conversion:

- ``autotype``: Automatic type detection
- ``int``: Integer casting
- ``float``: Float casting
- ``str``: String casting

**Example**:

.. code-block:: text

   #VVT: parameterize (type=int) : np = 1 2 4

### Type Options

**autotype** (default):

.. code-block:: text

   #VVT: parameterize (autotype) : value = 10 20.5 text

**int**:

.. code-block:: text

   #VVT: parameterize (type=int) : size = 10 20 30

**float**:

.. code-block:: text

   #VVT: parameterize (type=float) : ratio = 1.0 2.5 3.14

**str**:

.. code-block:: text

   #VVT: parameterize (type=str) : mode = fast slow medium

### Special Parameter Names

These names are forced to integer type:

- ``np``: Number of processes
- ``ndevice``: Number of devices
- ``nnode``: Number of nodes

**Example**:

.. code-block:: text

   #VVT: parameterize : np = 1 2 4  # Always integer

### Original String Preservation

The original string representation is preserved for execution path naming:

.. code-block:: text

   #VVT: parameterize : value = 1000000

The parameter value is:
- **Integer**: 1000000 (for computation)
- **String**: "1000000" (for path naming)

### Execution Path Naming

Parameter values are used in execution paths:

.. code-block:: text

   #VVT: parameterize : size = 10 20 30

Generates execution paths:
- ``test[size=10]``
- ``test[size=20]``
- ``test[size=30]``

Generator Parameterization
--------------------------

### Generator Option

Use ``generator`` option to execute a script:

.. code-block:: text

   #VVT: parameterize (generator) : params = script.py

### Script Execution

- Script executed in the ``.vvt`` file directory
- ``python`` or ``python3`` replaced by ``sys.executable``
- Output must be JSON lines

**Example**:

.. code-block:: text

   #VVT: parameterize (generator) : config = generate_params.py

### JSON Output Format

First JSON object/list gives parameter dictionaries:

.. code-block:: json

   [{"size": 10, "mode": "fast"}, {"size": 20, "mode": "slow"}]

### Dependency Output

Optional second JSON line gives dependencies:

.. code-block:: json

   [{"depends_on": ["setup_test"]}, {"depends_on": ["setup_test"]}]

### Dependency Count Validation

Dependency count must match parameterization count.

Examples
--------

### Simple Parameterization

.. code-block:: text

   #VVT: parameterize : size = 10 20 30

### Typed Parameterization

.. code-block:: text

   #VVT: parameterize (type=int) : np = 1 2 4

### Table Parameterization

.. code-block:: text

   #VVT: parameterize : size,mode = 10,fast 20,slow 30,medium

### Generator Parameterization

.. code-block:: text

   #VVT: parameterize (generator) : params = generate_config.py

Best Practices
--------------

1. **Use Descriptive Names**:

   .. code-block:: text

      #VVT: parameterize : workload_size = 100 1000 10000

2. **Type-Specific Parameters**:

   .. code-block:: text

      #VVT: parameterize (type=int) : np = 1 2 4

3. **Table for Complex Parameters**:

   .. code-block:: text

      #VVT: parameterize : size,mode,config = 10,fast,debug 20,slow,release

4. **Generator for Dynamic Parameters**:

   .. code-block:: text

      #VVT: parameterize (generator) : matrix = generate_matrix.py

See Also
--------

- :doc:`vvtest-directives`: Complete directive reference
- :doc:`file-format`: File format details
