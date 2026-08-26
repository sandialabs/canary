GitLab Issue Generation
========================

The canary_cdash extension includes a utility to synchronize CDash failures with GitLab issues. This is useful for tracking regressions in a project's issue tracker based on the CDash dashboard.

The make-gitlab-issues Command
----------------------------------

This command identifies failing tests on CDash and ensures corresponding issues exist in GitLab.

.. code-block:: console

   python3 -m canary report cdash make-gitlab-issues \
     --cdash-url https://cdash.example.org \
     --cdash-project MyProject \
     --gitlab-url https://gitlab.example.org/mygroup/myproject \
     --gitlab-api-url https://gitlab.example.org/api/v4 \
     --gitlab-project-id 123456

Authentication
--------------

The command requires a GitLab API access token with read/write privileges. This can be provided via:
1.  The -a ACCESS_TOKEN argument.
2.  The ACCESS_TOKEN environment variable.

Behavior
---------

*   **Issue Creation**: If a test fails on CDash but no matching issue exists in GitLab, a new issue is created.
*   **Issue Updates**: If an issue already exists, it is updated with a list of all currently failing realizations (sites, build types, compilers).
*   **Automatic Closing**: By default, if a test is no longer failing on CDash, the corresponding GitLab issue is closed and labeled as test::fixed. Use --dont-close-missing to disable this.
*   **Labeling**: Issues are tagged with:
    *   test::failed, test::diffed, or test::timeout based on the failure reason.
    *   system: <sitename> for each site where the test is failing.
    *   Stage::To Do.

Security Note
-------------

Never commit API tokens to version control. Use environment variables or a secure secrets manager.
