.. _centered-parameter-space:

How to generate a centered parameter space
==========================================

The centered parameter space computes parameter sets along multiple coordinate-based vectors, one per parameter, centered about the initial values.

The centered_parameter_space takes steps along each orthogonal dimension.  Each dimension is treated independently. The number of steps are taken in each direction, so that the total number of points in the parameter study is :math:`1+ 2\sum{n}`.

``.pyt``:

.. code-block:: python

   # test.pyt
   import sys
   import nvtest

   nvtest.directives.parameterize(
      "a,b", [(0, 5, 2), (0, 1, 2)], type=nvtest.enums.centered_parameter_space
   )

   def test():
      self = nvtest.test.instance
      print(f"{self.parameters.a}, {self.parameters.b")

   if __name__ == "__main__":
      sys.exit(test())


will produce two test cases, one with ``a=1`` and another with ``a=4``, each executed in their own test directory:

.. code-block:: console

   $ nvtest describe centered_space.pyt
   --- centered_space ------------
   File: .../centered_space.pyt
    Keywords:
    9 test cases:
   ├── centered_space[a=0,b=0]
   ├── centered_space[a=-10,b=0]
   ├── centered_space[a=-5,b=0]
   ├── centered_space[a=5,b=0]
   ├── centered_space[a=10,b=0]
   ├── centered_space[a=0,b=-2]
   ├── centered_space[a=0,b=-1]
   ├── centered_space[a=0,b=1]
   └── centered_space[a=0,b=2]
