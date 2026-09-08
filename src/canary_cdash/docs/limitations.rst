.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Limitations
===========

Known limitations and constraints of the ``canary_cdash`` extension.

General Limitations
-------------------

+----------------------------+--------------------------------------------------+
| Limitation                 | Description                                      |
+============================+==================================================+
| **External Dependency**    | Requires CDash server for full functionality     |
+----------------------------+--------------------------------------------------+
| **Network Required**       | Upload and query operations require network      |
+----------------------------+--------------------------------------------------+
| **No Offline Mode**        | Cannot generate reports without workspace        |
+----------------------------+--------------------------------------------------+
| **CDash Version**          | Compatible with specific CDash versions          |
+----------------------------+--------------------------------------------------+

XML Generation Limitations
---------------------------

+----------------------------+--------------------------------------------------+
| Limitation                 | Description                                      |
+============================+==================================================+
| **Memory Usage**           | Large workspaces may consume significant memory  |
+----------------------------+--------------------------------------------------+
| **Chunk Size Limits**      | Very large chunks may cause performance issues   |
+----------------------------+--------------------------------------------------+
| **File System**            | Requires write access to output directory        |
+----------------------------+--------------------------------------------------+
| **Metadata Availability**   | Limited by available Canary configuration       |
+----------------------------+--------------------------------------------------+

Upload Limitations
------------------

+----------------------------+--------------------------------------------------+
| Limitation                 | Description                                      |
+============================+==================================================+
| **Network Reliability**     | Upload failures may occur on unreliable networks|
+----------------------------+--------------------------------------------------+
| **Server Limits**           | CDash server may have file size limits          |
+----------------------------+--------------------------------------------------+
| **Authentication**          | Limited authentication options                  |
+----------------------------+--------------------------------------------------+
| **Proxy Support**           | No explicit proxy configuration support         |
+----------------------------+--------------------------------------------------+
| **Retry Logic**             | No automatic retry for failed uploads           |
+----------------------------+--------------------------------------------------+

GitLab Integration Limitations
-------------------------------

+----------------------------+--------------------------------------------------+
| Limitation                 | Description                                      |
+============================+==================================================+
| **API Rate Limits**         | Subject to GitLab API rate limits               |
+----------------------------+--------------------------------------------------+
| **Token Management**        | Requires careful token management               |
+----------------------------+--------------------------------------------------+
| **Project Access**          | Requires appropriate GitLab project access      |
+----------------------------+--------------------------------------------------+
| **Issue Volume**            | Large projects may generate many issues         |
+----------------------------+--------------------------------------------------+
| **Complexity**              | Issue management can become complex             |
+----------------------------+--------------------------------------------------+

Performance Considerations
--------------------------

+----------------------------+--------------------------------------------------+
| Consideration              | Impact                                           |
+============================+==================================================+
| **Large Workspaces**       | XML generation may be slow                       |
+----------------------------+--------------------------------------------------+
| **Many Tests**             | Chunking recommended for large test suites       |
+----------------------------+--------------------------------------------------+
| **Network Latency**        | Upload time depends on network speed             |
+----------------------------+--------------------------------------------------+
| **CDash Server Load**      | Server performance affects upload time           |
+----------------------------+--------------------------------------------------+

Troubleshooting
---------------

Common Issues and Solutions
~~~~~~~~~~~~~~~~~~~~~~~~~~~

**XML Generation Failures**:

- **Symptom**: XML generation fails or produces invalid XML
- **Solution**: Check workspace integrity, validate Canary configuration

**Upload Failures**:

- **Symptom**: Files fail to upload to CDash
- **Solution**: Check network connectivity, verify CDash server status

**Authentication Issues**:

- **Symptom**: CDash rejects uploads
- **Solution**: Verify site name and build configuration in CDash

**Memory Errors**:

- **Symptom**: Out of memory during XML generation
- **Solution**: Use smaller chunk sizes, process fewer jobs

**GitLab API Errors**:

- **Symptom**: GitLab issue creation fails
- **Solution**: Check token permissions, verify API access

Diagnostic Commands
~~~~~~~~~~~~~~~~~~~

Enable verbose logging:

.. code-block:: console

   $ python3 -m canary -v report cdash create --build MyBuild

Check CDash server status:

.. code-block:: console

   $ curl -I https://cdash.example.org

Test GitLab API access:

.. code-block:: console

   $ curl -H "Authorization: Bearer $GITLAB_TOKEN" \
       https://gitlab.example.org/api/v4/projects/12345

Best Practices for Reliability
------------------------------

1. **Validation**: Validate XML before upload
2. **Chunking**: Use appropriate chunk sizes
3. **Network**: Use reliable networks for uploads
4. **Monitoring**: Monitor upload status and errors
5. **Retry Logic**: Implement retry logic for transient failures
6. **Backup**: Backup XML files before upload
7. **Logging**: Enable verbose logging for diagnostics

Future Enhancements
-------------------

Potential areas for future improvement:

- **Proxy Support**: Explicit proxy configuration
- **Retry Logic**: Automatic retry for failed uploads
- **Authentication**: More authentication options
- **Performance**: Parallel upload support
- **Validation**: Enhanced XML validation
- **Monitoring**: Upload progress monitoring

See Also
--------

- :doc:`overview` - Extension overview
- :doc:`uploading` - Upload functionality
- :doc:`gitlab-issues` - GitLab integration
