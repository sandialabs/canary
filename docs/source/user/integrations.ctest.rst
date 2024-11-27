.. _integrations-ctest:

Run CTest tests
===============

In addition to :ref:`CMake integration<integrations-cmake>`, ``nvtest`` can run `CTest <https://cmake.org/cmake/help/latest/manual/ctest.1.html>`_ tests natively.  Simply pass the path to a CMake build directory containing CTest tests:

.. code-block:: console

    $ nvtest run CMAKE_BINARY_DIR

``nvtest`` will read the CTest instructions for each test added by ``add_test`` and run the test.

Supported CTest properties
--------------------------

The following `CTest properties <https://cmake.org/cmake/help/git-master/manual/cmake-properties.7.html#properties-on-tests>`_ are supported by ``nvtest``.

* `ATTACHED_FILES <https://cmake.org/cmake/help/git-master/prop_test/ATTACHED_FILES.html>`_
* `ATTACHED_FILES_ON_FAIL <https://cmake.org/cmake/help/git-master/prop_test/ATTACHED_FILES_ON_FAIL.html>`_
* `DEPENDS <https://cmake.org/cmake/help/git-master/prop_test/DEPENDS.html>`_
* `DISABLED <https://cmake.org/cmake/help/git-master/prop_test/DISABLED.html>`_
* `ENVIRONMENT <https://cmake.org/cmake/help/git-master/prop_test/ENVIRONMENT.html>`_
* `ENVIRONMENT_MODIFICATION <https://cmake.org/cmake/help/git-master/prop_test/ENVIRONMENT_MODIFICATION.html>`_
* `FAIL_REGULAR_EXPRESSION <https://cmake.org/cmake/help/git-master/prop_test/FAIL_REGULAR_EXPRESSION.html>`_
* `FIXTURES_CLEANUP <https://cmake.org/cmake/help/git-master/prop_test/FIXTURES_CLEANUP.html>`_
* `FIXTURES_REQUIRED <https://cmake.org/cmake/help/git-master/prop_test/FIXTURES_REQUIRED.html>`_
* `FIXTURES_SETUP <https://cmake.org/cmake/help/git-master/prop_test/FIXTURES_SETUP.html>`_
* `LABELS <https://cmake.org/cmake/help/git-master/prop_test/LABELS.html>`_
* `PASS_REGULAR_EXPRESSION <https://cmake.org/cmake/help/git-master/prop_test/PASS_REGULAR_EXPRESSION.html>`_
* `PROCESSORS <https://cmake.org/cmake/help/git-master/prop_test/PROCESSORS.html>`_
* `RESOURCE_GROUPS <https://cmake.org/cmake/help/git-master/prop_test/RESOURCE_GROUPS.html>`_
* `RUN_SERIAL <https://cmake.org/cmake/help/git-master/prop_test/RUN_SERIAL.html>`_
* `SKIP_REGULAR_EXPRESSION <https://cmake.org/cmake/help/git-master/prop_test/SKIP_REGULAR_EXPRESSION.html>`_
* `SKIP_RETURN_CODE <https://cmake.org/cmake/help/git-master/prop_test/SKIP_RETURN_CODE.html>`_
* `TIMEOUT <https://cmake.org/cmake/help/git-master/prop_test/TIMEOUT.html>`_
* `WILL_FAIL <https://cmake.org/cmake/help/git-master/prop_test/WILL_FAIL.html>`_
* `WORKING_DIRECTORY <https://cmake.org/cmake/help/git-master/prop_test/WORKING_DIRECTORY.html>`_

Unsupported CTest properties
----------------------------

The following `CTest properties <https://cmake.org/cmake/help/git-master/manual/cmake-properties.7.html#properties-on-tests>`_ are **not** supported by ``nvtest``.

* `COST <https://cmake.org/cmake/help/git-master/prop_test/COST.html>`_
* `GENERATED_RESOURCE_SPEC_FILE <https://cmake.org/cmake/help/git-master/prop_test/GENERATED_RESOURCE_SPEC_FILE.html>`_
* `MEASUREMENT <https://cmake.org/cmake/help/git-master/prop_test/MEASUREMENT.html>`_
* `PROCESSOR_AFFINITY <https://cmake.org/cmake/help/git-master/prop_test/PROCESSOR_AFFINITY.html>`_
* `REQUIRED_FILES <https://cmake.org/cmake/help/git-master/prop_test/REQUIRED_FILES.html>`_
* `RESOURCE_LOCK <https://cmake.org/cmake/help/git-master/prop_test/RESOURCE_LOCK.html>`_
* `TIMEOUT_AFTER_MATCH <https://cmake.org/cmake/help/git-master/prop_test/TIMEOUT_AFTER_MATCH.html>`_
* `TIMEOUT_SIGNAL_GRACE_PERIOD <https://cmake.org/cmake/help/git-master/prop_test/TIMEOUT_SIGNAL_GRACE_PERIOD.html>`_
* `TIMEOUT_SIGNAL_NAME <https://cmake.org/cmake/help/git-master/prop_test/TIMEOUT_SIGNAL_NAME.html>`_

.. note::

    Contact the ``nvtest`` developers if you require any one of these properties to run your test suite.

Differences in behavior from CTest
----------------------------------

DEPENDS
~~~~~~~

The CTest `DEPENDS <https://cmake.org/cmake/help/git-master/prop_test/DEPENDS.html>`_ property sets the execution order, but "the results of those tests are not considered, the dependency relationship is purely for order of execution".  In ``nvtest``, the results of the tests are considered.  See :ref:`directive-depends-on`.

RESOURCE_GROUPS
~~~~~~~~~~~~~~~

``nvtest`` does not currently read in a `CTest resource specification file <https://cmake.org/cmake/help/latest/manual/ctest.1.html#resource-specification-file>`_ and only recognizes the ``gpus`` `resource group <https://cmake.org/cmake/help/git-master/prop_test/RESOURCE_GROUPS.html>`_.  Eg, ``set_tests_properties(name PROPERTIES RESOURCE_GROUPS N:gpus,n)``

\*_REGULAR_EXPRESSION behavior
------------------------------

``*_REGULAR_EXPRESSION`` patterns are evaluated in the following order:

If ``PASS_REGULAR_EXPRESSION`` is defined
  set status to ``success`` if any pass regular expression matches, otherwise set status to ``failed``.

If ``SKIP_RETURN_CODE`` is defined
  set status to ``skipped`` if the test's return code is equal to ``SKIP_RETURN_CODE``

If ``SKIP_REGULAR_EXPRESSION`` is defined
  set status to ``skipped`` if any skip regular expression matches

If ``FAIL_REGULAR_EXPRESSION`` is defined
  set status to ``failed`` if any fail regular expression matches

Thus, if a test defines both ``PASS_REGULAR_EXPRESSION`` and ``FAIL_REGULAR_EXPRESSION`` and the output contains *both* patterns, the test will be marked as ``failed`` since the fail regular expression is evaluated last.
