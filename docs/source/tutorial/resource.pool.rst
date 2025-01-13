.. _tutorial-resource-pool:

The resource pool
=================

Compute resources available to ``nvtest`` are defined in the ``resource_pool`` :ref:`configuration <configuration>` field.  By default:

* The resource pool is automatically generated based on a machine probe and consists of a single node with ``N`` CPUs *and* 0 GPUs
* The number of CPUs ``N`` is determined by a system probe\ [1]_
* No other resource types are assumed to exist

To see the current resource pool, execute:

.. command-output:: nvtest config show resource_pool
    :nocache:

----------------------

Users have the flexibility to define the resource pool in a variety of ways using command line flags, configuration file, or a combination of both, depending on the specific requirements of their computing environment.

.. note::

  * Any resources other than ``cpus`` and ``gpus`` must be defined by the user.
  * ``nvtest`` assumes a default GPU count of 0

-----------------------

.. [1] The CPU IDs are ``nvtest``'s internal IDs (number ``0..N-1``) and may not represent actual hardware IDs.
