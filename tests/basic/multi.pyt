#!/usr/bin/env python3

import nvtest

nvtest.directives.name("baz")
nvtest.directives.parameterize("a,b", [(10, 11), (20, 21)], testname="baz")

nvtest.directives.name("foo")
#nvtest.directives.parameterize("c,d", [(10, 11), (20, 21)], testname="foo")
nvtest.directives.depends_on("baz.*", testname="foo")

#nvtest.directives.name("spam")
#nvtest.directives.parameterize("e,f", [(0, 1), (1, 2)], testname="spam")
#nvtest.directives.depends_on("foo.c=10.d=11", testname="spam")
#nvtest.directives.depends_on("foo", testname="spam")
