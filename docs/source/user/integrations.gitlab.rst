.. _integrations-gitlab:

Integrate with GitLab
=====================

Upon completion of a test session, launched in a GitLab merge request environment, ``canary`` can report back to the merge request the status of the test session.  To enable this integration, define the variable ``GITLAB_ACCESS_TOKEN`` in your runner's environment with an access token that has GitLab API read/write permissions.

In addition to reporting back to the merge request, ``canary`` can automatically create a :ref:`CDash <usage-cdash>` report and post a link in the merge request report.  To enable this integration, define the following variables in your runner's environment:

* ``MERGE_REQUEST_CDASH_URL``: url of the CDash site
* ``MERGE_REQUEST_CDASH_PROJECT``: name of CDash project
* ``MERGE_REQUEST_CDASH_SITE``: The name of the CDash site (default: ``os.node().uname``)
* ``MERGE_REQUEST_CDASH_TRACK``: The CDash track to post to (default: ``Merge Request``)
