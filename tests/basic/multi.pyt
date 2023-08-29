#!/usr/bin/env python3

import nvtest

nvtest.mark.name("baz")
nvtest.mark.parameterize("a,b", [(10, 11), (20, 21)], testname="baz")

nvtest.mark.name("foo")
#nvtest.mark.parameterize("c,d", [(10, 11), (20, 21)], testname="foo")
nvtest.mark.depends_on("baz.*", testname="foo")

#nvtest.mark.name("spam")
#nvtest.mark.parameterize("e,f", [(0, 1), (1, 2)], testname="spam")
#nvtest.mark.depends_on("foo.c=10.d=11", testname="spam")
#nvtest.mark.depends_on("foo", testname="spam")
