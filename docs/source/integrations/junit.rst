.. _integrations-junit:

JUnit integration
=================

``nvtest`` can emit `JUnit XML files <https://www.ibm.com/docs/en/developer-for-zos/16.0?topic=formats-junit-xml-format>`_ for a completed test session.  The JUnit XML report format is a standardized structure for representing the results of unit tests, commonly used in continuous integration and continuous deployment (CI/CD) pipelines. This format, which is based on XML (Extensible Markup Language), allows for the systematic recording of test outcomes, including details such as the number of tests run, passed, failed, and skipped, as well as specific error messages and stack traces for failed tests.

See :ref:`howto-junit` for examples of creating JUnit formatted reports.

``nvtest`` supports the following tags and attributes:

.. code-block:: xml

    <?xml version="1.0" encoding="UTF-8"?>

    <!-- <testsuites> Usually the root element of a JUnit XML file.

    name        Name of the entire test run (default: NVtest session)
    tests       Total number of tests in this file
    failures    Total number of failed tests in this file
    skipped     Total number of skipped tests in this file
    time        Aggregated time of all tests in this file in seconds
    timestamp   Date and time of when the test run was executed (in ISO 8601 format)
    -->

    <testsuites name="..." tests="..." failures="..." skipped="..." time="..." timestamp="...">

         <!-- <testsuite> A test suite represents tests in a common folder.

        name        Name of the test suite (folder name)
        tests       Total number of tests in this suite
        failures    Total number of failed tests in this suite
        skipped     Total number of skipped tests in this suite
        time        Aggregated time of all tests in this file in seconds
        timestamp   Date and time of when the test suite was executed (in ISO 8601 format)
        -->
        <testsuite name="..." time="...">
            <!-- <testcase> There are one or more test cases in a test suite.

            name        The name of this test case
            classname   The name of the parent folder (same as the suite's name)
            time        Execution time of the test in seconds
            file        Source code file of this test case
            line        Source code line number of the start of this test case
            -->
            <testcase name="..." classname="..." time="..."/>
        </testsuite>
    </testsuites>
