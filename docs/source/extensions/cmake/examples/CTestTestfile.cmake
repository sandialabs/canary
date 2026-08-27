# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

add_test(ctest_test "ls" "/")
add_test(resource_group_test_1 "./resource_group_test_1.py")
set_tests_properties(resource_group_test_1 PROPERTIES PROCESSORS 2 RESOURCE_GROUPS 2,gpus:1 PASS_REGULAR_EXPRESSION "TEST PASSED!")
add_test(resource_group_test_2 "./resource_group_test_2.py")
set_tests_properties(resource_group_test_2 PROPERTIES PROCESSORS 2 RESOURCE_GROUPS gpus:1,gpus:1 PASS_REGULAR_EXPRESSION "TEST CERTAINLY PASSED!")
