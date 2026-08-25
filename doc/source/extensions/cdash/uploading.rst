.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Uploading to CDash
==================

Post CDash XML files to CDash servers using the ``post`` command.

Command Reference
-----------------

.. code-block:: console

   $ python3 -m canary report cdash post -h

Options:

+------------------------------------+--------------------------------------------------+
| Option                             | Description                                      |
+====================================+==================================================+
| ``--project CDASH_PROJECT``        | CDash project name [required]                    |
+------------------------------------+--------------------------------------------------+
| ``--url CDASH_URL``                | Base CDash URL [required]                        |
+------------------------------------+--------------------------------------------------+
| ``--done``                         | Post Done.xml to finalize build                   |
+------------------------------------+--------------------------------------------------+
| ``files...``                       | XML files to upload [required]                    |
+------------------------------------+--------------------------------------------------+

Basic Upload
------------

Upload single XML file:

.. code-block:: console

   $ python3 -m canary report cdash post \
       --project MyProject \
       --url https://cdash.example.org \
       CDASH/Test-0.xml

Upload multiple files:

.. code-block:: console

   $ python3 -m canary report cdash post \
       --project MyProject \
       --url https://cdash.example.org \
       CDASH/*.xml

Upload with Done.xml
--------------------

Finalize build by posting Done.xml:

.. code-block:: console

   $ python3 -m canary report cdash post \
       --project MyProject \
       --url https://cdash.example.org \
       --done \
       CDASH/Test-0.xml

The ``--done`` option:

1. Creates a ``Done.xml`` file
2. Uploads it to CDash
3. Finalizes the build
4. Returns the build summary URL

Upload Process
--------------

The upload process:

1. **Validation**: Validates XML files against CDash schema
2. **Metadata Extraction**: Reads site, build, and timestamp from first XML file
3. **Upload**: Posts each XML file to CDash server
4. **Build ID**: Retrieves build ID from CDash
5. **Done.xml**: Optionally creates and uploads Done.xml
6. **URL Return**: Returns build summary URL

Requirements
------------

Network Requirements
~~~~~~~~~~~~~~~~~~~~

- **Internet Access**: Required to reach CDash server
- **Firewall**: Must allow outbound HTTP/HTTPS to CDash URL
- **Proxy**: Configure proxy if required (not currently supported by canary_cdash)

CDash Server Requirements
~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Configured Project**: CDash project must exist
- **Upload Permissions**: Server must accept uploads
- **Authentication**: Server must be configured to accept uploads from your site
- **Network Accessibility**: Server must be reachable from your network

Error Handling
--------------

Upload errors are logged but do not stop the process:

- Individual file upload failures are logged as warnings
- Process continues with remaining files
- Final status indicates number of failed uploads

Common Issues
~~~~~~~~~~~~~

**Network Connectivity**:

- Verify CDash URL is correct and reachable
- Check firewall/proxy settings
- Test connectivity with ``curl`` or ``wget``

**Authentication Issues**:

- Verify CDash project is configured to accept uploads
- Check that site name matches CDash configuration
- Ensure build name is valid for the project

**XML Validation Errors**:

- Verify XML files are valid CDash format
- Check that required fields are present
- Validate XML against CDash schema

**Build Already Exists**:

- Use unique build stamps to avoid conflicts
- Consider using ``--track`` for different build types
- Ensure build names are unique per site

Diagnostics
-----------

Enable verbose logging for debugging:

.. code-block:: console

   $ python3 -m canary -v report cdash post \
       --project MyProject \
       --url https://cdash.example.org \
       CDASH/Test-0.xml

Check CDash server logs for upload details.

Proxy Configuration
-------------------

Currently, ``canary_cdash`` does not support explicit proxy configuration. Use system proxy settings or environment variables:

.. code-block:: console

   $ export HTTP_PROXY=http://proxy.example.com:8080
   $ export HTTPS_PROXY=http://proxy.example.com:8080
   $ python3 -m canary report cdash post --project MyProject --url https://cdash.example.org CDASH/Test-0.xml

Security Considerations
-----------------------

- **Credentials**: CDash uploads typically don't require credentials in the URL
- **HTTPS**: Always use HTTPS for CDash URLs
- **Network Security**: Ensure network between Canary and CDash is secure
- **Data Privacy**: CDash XML may contain sensitive information

Performance
-----------

Upload performance considerations:

- **Chunk Size**: Smaller chunks upload faster but create more files
- **Network Speed**: Large XML files may take significant time
- **Server Load**: CDash server performance affects upload time
- **Parallel Uploads**: Currently sequential (not parallel)

Best Practices
--------------

1. **Test Locally**: Generate XML locally before uploading
2. **Validate XML**: Check XML validity before upload
3. **Use Unique Build Stamps**: Avoid conflicts with existing builds
4. **Monitor Uploads**: Check CDash dashboard after upload
5. **Handle Errors**: Implement retry logic if needed
6. **Secure Network**: Use secure networks for uploads

See Also
--------

- :doc:`overview` - Extension overview
- :doc:`xml-generation` - XML generation
- :doc:`summaries` - CDash summaries