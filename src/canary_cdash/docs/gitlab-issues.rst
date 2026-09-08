.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

GitLab Issues
=============

Create GitLab issues from CDash test failures.

Command Reference
-----------------

.. code-block:: console

   $ python3 -m canary report cdash make-gitlab-issues -h

Options:

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Option
     - Description
   * - ``-a TOKEN``
     - GitLab access token
   * - ``--cdash-url URL``
     - Base CDash URL [required]
   * - ``--cdash-project PROJECT``
     - CDash project name [required]
   * - ``--gitlab-url URL``
     - GitLab project URL [required]
   * - ``--gitlab-api-url URL``
     - GitLab API URL [required]
   * - ``--gitlab-project-id ID``
     - GitLab project ID [required]
   * - ``-d DATE``
     - Date for failures (YYYY-MM-DD)
   * - ``-f GROUPS``
     - Filter groups (repeatable)
   * - ``--skip-site SITE``
     - Skip site (regex pattern, repeatable)
   * - ``--dont-close-missing``
     - Don't close issues for missing failures

Basic Usage
-----------

Create issues from today's failures:

.. code-block:: console

   $ python3 -m canary report cdash make-gitlab-issues \
       -a "$GITLAB_TOKEN" \
       --cdash-url https://cdash.example.org \
       --cdash-project MyProject \
       --gitlab-url https://gitlab.example.org/mygroup/myproject \
       --gitlab-api-url https://gitlab.example.org/api/v4 \
       --gitlab-project-id 12345

Create issues for specific date:

.. code-block:: console

   $ python3 -m canary report cdash make-gitlab-issues \
       -a "$GITLAB_TOKEN" \
       --cdash-url https://cdash.example.org \
       --cdash-project MyProject \
       --gitlab-project-id 12345 \
       -d 2024-01-01

Filter by Groups
~~~~~~~~~~~~~~~~

.. code-block:: console

   $ python3 -m canary report cdash make-gitlab-issues \
       -a "$GITLAB_TOKEN" \
       --cdash-url https://cdash.example.org \
       --cdash-project MyProject \
       --gitlab-project-id 12345 \
       -f Nightly

Skip Specific Sites
~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   $ python3 -m canary report cdash make-gitlab-issues \
       -a "$GITLAB_TOKEN" \
       --cdash-url https://cdash.example.org \
       --cdash-project MyProject \
       --gitlab-project-id 12345 \
       --skip-site "test-.*" --skip-site "backup-.*"

Issue Creation Process
----------------------

1. **Query CDash**: Retrieve test failures from CDash
2. **Filter Results**: Apply date, group, and site filters
3. **Create Issues**: Create GitLab issues for new failures
4. **Update Issues**: Update existing issues with new information
5. **Close Issues**: Close issues for fixed tests (unless ``--dont-close-missing``)

Requirements
------------

GitLab Requirements
~~~~~~~~~~~~~~~~~~~

- **Access Token**: GitLab API token with read/write privileges
- **Project ID**: GitLab project integer ID
- **API Access**: GitLab API must be accessible
- **Permissions**: Token must have issue creation permissions

CDash Requirements
~~~~~~~~~~~~~~~~~~

- **Read Access**: Requires read access to CDash project
- **Failure Data**: CDash must have failure data available
- **Network Access**: CDash server must be accessible

Issue Format
------------

GitLab issues include:

- **Title**: Descriptive title with test name and failure type
- **Description**: Detailed failure information from CDash
- **Labels**: GitLab labels for categorization
- **Links**: Links to CDash build and test details
- **Metadata**: Build information and failure context

Issue Management
----------------

Issue Lifecycle
~~~~~~~~~~~~~~~

1. **Creation**: Issue created for new test failure
2. **Update**: Issue updated when failure persists
3. **Resolution**: Issue closed when test passes
4. **Reopening**: Issue reopened if failure recurs

Issue Tracking
~~~~~~~~~~~~~~

The system tracks:

- **Failure History**: When failures first appeared
- **Resolution History**: When failures were fixed
- **Recurrence**: If failures reappear after being fixed

Best Practices
--------------

1. **Token Security**: Protect GitLab access tokens
2. **Rate Limiting**: Be aware of GitLab API rate limits
3. **Issue Volume**: Monitor issue creation volume
4. **Filtering**: Use filters to focus on relevant failures
5. **Automation**: Automate issue creation in CI/CD pipelines

Limitations
-----------

- **API Limits**: Subject to GitLab API rate limits
- **Network Dependencies**: Requires both CDash and GitLab access
- **Complexity**: Issue management can become complex for large projects
- **Permissions**: Requires appropriate permissions on both systems

Security Considerations
-----------------------

- **Token Protection**: Never commit tokens to version control
- **Environment Variables**: Use environment variables for tokens
- **Network Security**: Use secure networks for API calls
- **Access Control**: Limit who can configure issue creation

Example Configuration
---------------------

Environment variables:

.. code-block:: console

   $ export GITLAB_TOKEN="your-access-token-here"
   $ export CDASH_URL="https://cdash.example.org"
   $ export CDASH_PROJECT="MyProject"
   $ export GITLAB_URL="https://gitlab.example.org/mygroup/myproject"
   $ export GITLAB_API_URL="https://gitlab.example.org/api/v4"
   $ export GITLAB_PROJECT_ID="12345"

Automated issue creation:

.. code-block:: console

   $ python3 -m canary report cdash make-gitlab-issues \
       -a "$GITLAB_TOKEN" \
       --cdash-url "$CDASH_URL" \
       --cdash-project "$CDASH_PROJECT" \
       --gitlab-url "$GITLAB_URL" \
       --gitlab-api-url "$GITLAB_API_URL" \
       --gitlab-project-id "$GITLAB_PROJECT_ID"

See Also
--------

- :doc:`overview` - Extension overview
- :doc:`summaries` - CDash summaries