As an analysis tool
-------------------

.. revealjs-fragments::

   Canary excels as a workflow tool for analysts.

.. revealjs-break::
    :data-transition: none

.. code-block:: python

    canary.directives.copy("$NAME.inp.in")
    canary.directives.parameterize("PARAM", (0, 1))
    canary.directives.parameterize("cpus", (40,))
    canary.directives.generate_composite_base_case()

.. container:: fragment

   .. code-block:: python

       def run(job: canary.TestInstance):
           preprocess(f"{job.family}.inp.in", PARAM=job.parameters.PARAM)
           mpi = canary.Executable("mpiexec")
           mpi("-n", str(job.cpus), "my-program", f"{job.family}.inp")
           plot_something_cool(job)

.. container:: fragment

   .. code-block:: python

       def analyze(job: canary.TestMultiInstance):
           f1 = job.dependencies[0]
           f2 = job.dependencies[1]
           compare_responses(f1, f2)

.. container:: fragment

   .. code-block:: python

       if __name__ == "__main__":
           job = canary.get_instance()
           if isinstance(job, canary.TestMultiInstance):
               analyze(job)
           else:
               run(job)
