add_test([=[my-test]=] "ls .")
set_tests_properties([=[my-test]=] PROPERTIES  PASS_REGULAR_EXPRESSION "this test has a new
line;and another
one" _BACKTRACE_TRIPLES "f;4;add_test;f;0;")
