Installing nvtest
=================

.. code-block:: console

    python3 -m venv venv
    source venv/bin/activate
    python3 -m pip install \
      --trusted-host=cee-gitlab.sandia.gov \
      --index-url=https://nexus.web.sandia.gov/repository/pypi-proxy/simple \
      --extra-index-url=https://cee-gitlab.sandia.gov/api/v4/projects/51750/packages/pypi/simple \
      nvtest[pbs,slurm,flux]
