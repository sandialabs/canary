What does a test look like?
---------------------------

.. revealjs-fragments::

    * Tests are python scripts with ``.pyt`` extension
    * Test passes if exit code is 0, fails otherwise

.. revealjs-break::
  :data-transition: none

Consider ``add.pyt``:

.. code-block:: python

   import sys

   def add(a: int, b: int) -> int:
       return a + b

   def test() -> int:
       assert add(2, 2) == 4
       return 0

   if __name__ == "__main__":
       sys.exit(test())

.. revealjs-break::
  :data-transition: none

To run the test:

.. code-block:: console

  canary run [options] PATH

.. revealjs-fragments::

   * Canary scans ``PATH`` for ``.pyt`` files; and
   * For each ``.pyt``, Canary file executes [2]_

     .. code-block:: console

        mkdir -p TestResults/add
        cp PATH/add.pyt TestResults/add
        cd TestResults/add
        python3 add.pyt

.. container:: fragment

  .. [2] For illustration only.  Internally, Canary runs each test in its own sandbox, updates its database, etc.


Tests can be parameterized
^^^^^^^^^^^^^^^^^^^^^^^^^^

Consider ``scale.pyt``

.. code-block:: python

   import sys
   import canary

   canary.directives.parameterize("a", (1, 2, 3))


   def scale(a: int, x: int) -> int:
       return a * x


   def test() -> int:
       inst = canary.get_instance()
       a = inst.parameters.a
       assert scale(a, 2) == a * 2
       return 0


   if __name__ == "__main__":
       sys.exit(test())

.. revealjs-break::
  :data-transition: none

The directive:

.. code-block:: python

    canary.directives.parameterize("a", (1, 2, 3))

generates 3 test cases:

.. raw:: html

   <div style="display:flex; justify-content:center;">
     <svg width="980" height="260" viewBox="0 0 980 260" xmlns="http://www.w3.org/2000/svg">
       <defs>
         <style>
           .node  { fill: rgba(255,255,255,0.06); stroke: rgba(255,255,255,0.60); stroke-width: 2; }
           .label { fill: rgba(255,255,255,0.92); font: 22px ui-monospace, Menlo, Consolas, monospace; }
           .conn  { fill: none; stroke: rgba(255,255,255,0.70); stroke-width: 3; }
         </style>

         <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5"
                 markerWidth="2.0" markerHeight="2.0" orient="auto">
           <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(255,255,255,0.70)"/>
         </marker>
       </defs>

       <!-- Top node -->
       <rect class="node" x="390" y="25" width="200" height="60" rx="10"/>
       <text class="label" x="490" y="55" text-anchor="middle" dominant-baseline="middle">scale.pyt</text>

       <!-- Child nodes (3 cases) -->
       <rect class="node" x="140" y="150" width="220" height="60" rx="10"/>
       <text class="label" x="250" y="180" text-anchor="middle" dominant-baseline="middle">scale[a=1]</text>

       <rect class="node" x="380" y="150" width="220" height="60" rx="10"/>
       <text class="label" x="490" y="180" text-anchor="middle" dominant-baseline="middle">scale[a=2]</text>

       <rect class="node" x="620" y="150" width="220" height="60" rx="10"/>
       <text class="label" x="730" y="180" text-anchor="middle" dominant-baseline="middle">scale[a=3]</text>

       <!-- Elbow connectors -->
       <path class="conn" marker-end="url(#arrow)"
             d="M 490 85 L 490 115 L 250 115 L 250 150" />
       <path class="conn" marker-end="url(#arrow)"
             d="M 490 85 L 490 125 L 490 125 L 490 150" />
       <path class="conn" marker-end="url(#arrow)"
             d="M 490 85 L 490 115 L 730 115 L 730 150" />
     </svg>
   </div>

.. revealjs-break::
  :data-transition: none

Multiple ``parameterize`` directives are combined by Cartesian product

.. code-block:: python

   canary.directives.parameterize("a", (1, 2, 3))
   canary.directives.parameterize("b", ("a", "b", "c"))

.. raw:: html

   <div style="display:flex; justify-content:center;">
     <svg width="980" height="300" viewBox="0 0 980 300" xmlns="http://www.w3.org/2000/svg">
       <defs>
         <style>
           .node  { fill: rgba(255,255,255,0.06); stroke: rgba(255,255,255,0.60); stroke-width: 2; }
           .label { fill: rgba(255,255,255,0.92); font: 20px ui-monospace, Menlo, Consolas, monospace; }
           .conn  { fill: none; stroke: rgba(255,255,255,0.70); stroke-width: 3; }
         </style>

         <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5"
                 markerWidth="2.0" markerHeight="2.0" orient="auto">
           <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(255,255,255,0.70)"/>
         </marker>
       </defs>

       <!-- Top node (w=150, centered at x=490 => x=415) -->
       <rect class="node" x="415" y="25" width="150" height="60" rx="10"/>
       <text class="label" x="490" y="55" text-anchor="middle" dominant-baseline="middle">scale.pyt</text>

       <!-- Child nodes (w=180) -->
       <rect class="node" x="120" y="170" width="180" height="60" rx="10"/>
       <text class="label" x="210" y="200" text-anchor="middle" dominant-baseline="middle">scale[a=1,b=a]</text>

       <rect class="node" x="400" y="170" width="180" height="60" rx="10"/>
       <text class="label" x="490" y="200" text-anchor="middle" dominant-baseline="middle">scale[a=1,b=b]</text>

       <rect class="node" x="680" y="170" width="180" height="60" rx="10"/>
       <text class="label" x="770" y="200" text-anchor="middle" dominant-baseline="middle">scale[a=3,b=c]</text>

       <!-- Floating ellipsis (no box, no arrow) -->
       <text class="label" x="630" y="200" text-anchor="middle" dominant-baseline="middle">...</text>

       <!-- Elbow connectors (3 only) -->
       <path class="conn" marker-end="url(#arrow)"
             d="M 490 85 L 490 125 L 210 125 L 210 170" />
       <path class="conn" marker-end="url(#arrow)"
             d="M 490 85 L 490 140 L 490 140 L 490 170" />
       <path class="conn" marker-end="url(#arrow)"
             d="M 490 85 L 490 125 L 770 125 L 770 170" />
     </svg>
   </div>

Tests can depend on other tests
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    # -- a.pyt --
    import canary

    canary.directives.parameterize("a", [0, 1])

    def test() -> int:
        ...

.. code-block:: python

    # -- b.pyt --
    import canary

    canary.directives.parameterize("b", [2, 3])
    canary.directives.depends_on("a[a=0]")

    def test() -> int:
        inst = canary.get_instance()
        a = inst.dependencies[0]

Tests can copy resources into their execution sandbox
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    import sys
    import canary

    canary.directives.parameterize("cpus", (1, 4, 8))
    canary.directives.copy("$NAME.inp")

    def test() -> int:
        inst = canary.get_instance()
        mpi = canary.Executable("mpiexec")
        mpi("-n", str(inst.cpus), f"{inst.family}.inp")
        return 0

    if __name__ == "__main__":
        sys.exit(test())

Composite base case
^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    # base.pyt
    import sys
    import canary

    canary.directives.parameterize("size", [1, 2, 4, 8, 16])
    canary.directives.generate_composite_base_case()

.. container:: fragment

   .. raw:: html

      <div style="display:flex; justify-content:center;">
        <svg width="980" height="320" viewBox="0 0 980 320" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <style>
              .node  { fill: rgba(255,255,255,0.06); stroke: rgba(255,255,255,0.60); stroke-width: 2; }
              .label { fill: rgba(255,255,255,0.92); font: 20px ui-monospace, Menlo, Consolas, monospace; }
              .conn  { fill: none; stroke: rgba(255,255,255,0.70); stroke-width: 3; }
            </style>

            <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5"
                    markerWidth="2.0" markerHeight="2.0" orient="auto">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(255,255,255,0.70)"/>
            </marker>
          </defs>

          <!-- Row 1: file -->
          <rect class="node" x="390" y="20" width="200" height="60" rx="10"/>
          <text class="label" x="490" y="50" text-anchor="middle" dominant-baseline="middle">base.pyt</text>

          <!-- Row 2: base case -->
          <rect class="node" x="420" y="110" width="140" height="60" rx="10"/>
          <text class="label" x="490" y="140" text-anchor="middle" dominant-baseline="middle">base</text>

          <!-- Row 3: parameterized cases (5 across, symmetric) -->
          <rect class="node" x="20"  y="230" width="180" height="60" rx="10"/>
          <text class="label" x="110" y="260" text-anchor="middle" dominant-baseline="middle">base[size=1]</text>

          <rect class="node" x="210" y="230" width="180" height="60" rx="10"/>
          <text class="label" x="300" y="260" text-anchor="middle" dominant-baseline="middle">base[size=2]</text>

          <rect class="node" x="400" y="230" width="180" height="60" rx="10"/>
          <text class="label" x="490" y="260" text-anchor="middle" dominant-baseline="middle">base[size=4]</text>

          <rect class="node" x="590" y="230" width="180" height="60" rx="10"/>
          <text class="label" x="680" y="260" text-anchor="middle" dominant-baseline="middle">base[size=8]</text>

          <rect class="node" x="780" y="230" width="180" height="60" rx="10"/>
          <text class="label" x="870" y="260" text-anchor="middle" dominant-baseline="middle">base[size=16]</text>

          <!-- Connectors -->
          <path class="conn" marker-end="url(#arrow)" d="M 490 80 L 490 110" />

          <path class="conn" marker-end="url(#arrow)" d="M 490 170 L 490 200 L 110 200 L 110 230" />
          <path class="conn" marker-end="url(#arrow)" d="M 490 170 L 490 205 L 300 205 L 300 230" />
          <path class="conn" marker-end="url(#arrow)" d="M 490 170 L 490 220 L 490 220 L 490 230" />
          <path class="conn" marker-end="url(#arrow)" d="M 490 170 L 490 205 L 680 205 L 680 230" />
          <path class="conn" marker-end="url(#arrow)" d="M 490 170 L 490 200 L 870 200 L 870 230" />
        </svg>
      </div>

   where ``base`` depends on all ``base[size=*]`` cases

.. revealjs-break::
  :data-transition: none

You may want to use the base case for doing a convergence study:

.. code-block:: python

   inst = canary.get_instance()
   if isinstance(inst, canary.TestMultiInstance):
       # do something with inst.dependencies


There are many other directives
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 40 60
   :class: smalltable

   * - ``copy(*files)``
     - Copy one or more files into the execution directory.
   * - ``depends_on(arg)``
     - Declare dependencies that must run first.
   * - ``exclusive()``
     - Mark the test as exclusive.
   * - ``generate_composite_base_case()``
     - Create an analysis base case that depends on other cases generated by the file.
   * - ``enable(arg)``
     - Explicitly enable/disable a test.
   * - ``keywords(*args)``
     - Attach keywords to a test for filtering/selection.
   * - ``link(*files)``
     - Link files into the execution directory.
   * - ``parameterize(names, values)``
     - Generate multiple test invocations by parameterizing inputs.
   * - ``skipif(arg, reason)``
     - Conditionally skip a test.
   * - ``timeout(arg)``
     - Set a per-test timeout.
   * - ``xdiff()``
     - Mark the test as expected to diff.
   * - ``xfail(code=-1)``
     - Mark the test as expected to fail; optionally require a specific exit code.
