.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _integrations-cdash:

CDash Reporting Overview
========================

The ``canary_cdash`` extension is a **reporting extension** for Canary that provides CDash integration. It operates on completed Canary workspace results to generate CDash-compatible XML reports.

Extension Type
--------------

- **Reporting Extension**: Generates reports from Canary workspace results
- **CDash Integration**: Creates CDash-compatible XML and uploads to CDash servers
- **Plugin Architecture**: Uses Canary's plugin system for customization

Key Features
------------

1. **XML Generation**: Creates CDash-compatible XML files from Canary job results
2. **Chunking Support**: Splits large reports into manageable chunks
3. **Metadata Collection**: Gathers system and build information automatically
4. **Subproject Support**: Organizes tests by subprojects using labels
5. **Artifact Handling**: Attaches files and captures job output
6. **Status Mapping**: Maps Canary job status to CDash test status
7. **Upload Functionality**: Posts XML reports to CDash servers
8. **Summary Generation**: Creates HTML summaries of CDash dashboards
9. **GitLab Integration**: Generates GitLab issues from CDash failures

Architecture
------------

The ``canary_cdash`` extension follows Canary's reporting architecture:

1. **Workspace Analysis**: Reads completed Canary workspace results
2. **XML Generation**: Creates CDash XML from job data
3. **Customization**: Applies plugin hooks for custom behavior
4. **Upload**: Posts XML to CDash servers (optional)
5. **Summary**: Generates HTML summaries (optional)
6. **Issue Creation**: Creates GitLab issues from failures (optional)

Workflow
--------

Typical CDash reporting workflow:

.. code-block:: console

   # Generate CDash XML from Canary workspace
   $ python3 -m canary report cdash create --build MyBuild --site MySite

   # Post XML to CDash server
   $ python3 -m canary report cdash post --project MyProject --url https://cdash.example.org CDASH/*.xml

   # Generate HTML summary
   $ python3 -m canary report cdash summary --project MyProject --url https://cdash.example.org

   # Create GitLab issues from failures
   $ python3 -m canary report cdash make-gitlab-issues --cdash-url https://cdash.example.org --cdash-project MyProject

Relationship to Canary Core
---------------------------

The ``canary_cdash`` extension:

- ✅ **Operates on completed workspace results**
- ✅ **Generates CDash-compatible XML**
- ✅ **Uploads XML to external CDash servers**
- ✅ **Generates HTML summaries from CDash**
- ✅ **Creates GitLab issues from CDash failures**
- ❌ **Does not define job formats**
- ❌ **Does not schedule or execute jobs**
- ❌ **Does not modify Canary core behavior**

External System Requirements
-----------------------------

CDash Integration
~~~~~~~~~~~~~~~~~

- **CDash Server**: Requires configured CDash project
- **Network Access**: Requires internet access to CDash server
- **Authentication**: CDash server must accept uploads
- **Project Configuration**: CDash project must be properly configured

GitLab Integration
~~~~~~~~~~~~~~~~~~

- **GitLab API**: Requires GitLab API access
- **Access Token**: Requires GitLab API token with read/write privileges
- **Project ID**: Requires GitLab project ID
- **Network Access**: Requires internet access to GitLab server

See Also
--------

- :doc:`reporter-plugin` - Reporter plugin architecture
- :doc:`xml-generation` - XML generation details
- :doc:`uploading` - Upload functionality
- :doc:`gitlab-issues` - GitLab issue generation