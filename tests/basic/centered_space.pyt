#!/usr/bin/env python3
import nvtest
nvtest.directives.processors(4)
nvtest.directives.parameterize(
    "a,b", [(0, 5, 2), (0, 1, 2)], type=nvtest.enums.centered_parameter_space
)
