.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _canary-cmake:

CMake, CTest, and CDash
=======================

``canary`` includes built-in support for CMake-based projects. With this integration you can

* add CMake functions and targets that generate ``canary`` test scripts and configuration directly from your ``CMakeLists.txt``;
* run CTest tests from an existing CMake build tree; and
* generate CDash XML reports and upload them to a CDash server.

.. toctree::
   :maxdepth: 1
   :caption: Contents:

   CMake<usage.cmake.cmake>
   CTest<usage.cmake.ctest>
   CDash<usage.cmake.cdash>
