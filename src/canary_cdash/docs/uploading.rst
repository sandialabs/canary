Uploading to CDash
===================

Once XML files are generated, they must be uploaded to the CDash server to be processed and displayed on the dashboard.

The post Command
-------------------

The canary report cdash post command uses curl to upload files to the CDash submit.php endpoint.

.. code-block:: console

   python3 -m canary report cdash post --project MyProject --url https://cdash.example.org CDASH/Test-0.xml

Options
-------

*   **--project PROJECT**: The name of the project on the CDash server.
*   **--url URL**: The base URL of the CDash installation (do not include the project name).
*   **--done**: Uploads a Done.xml file, signaling to CDash that the build is complete.

Network and Security
--------------------

*   **Network Access**: Uploading requires outbound HTTP access to the CDash server.
*   **Proxy Settings**: The extension intentionally disables proxy settings during the upload process to ensure connectivity to internal CDash servers.
*   **Credentials**: CDash typically identifies builds by the combination of Project, Site, Build Name, and Stamp. Ensure these are consistent across your reporting pipeline.
