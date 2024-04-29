"""\
Before running a test, ``nvtest`` reads the test file looking for "test
directives".   Test directives are instructions for how to setup and allocate
resources needed by the test.  The ``.pyt`` and ``.vvt`` file types use
different directive styles.  In the ``.pyt`` file type, directives are python
commands contained in the ``nvtest.directives`` namespace.  In the ``.vvt`` file
type, text directives are preceded with ``#VVT:`` and ``nvtest`` will stop
processing further ``#VVT:`` directives once the first non-comment
non-whitespace line has been reached in the test script.

The general format for a directive is

``.pyt``:

.. code-block:: python

   import nvtest
   nvtest.directives.directive_name(*args, **kwargs)

``.vvt``:

.. code-block:: python

    #VVT: directive_name [<option spec>] [: <args>]

where the optional ``option spec`` takes the form:

.. code-block:: console

    (name=value[, ...])

``.vvt`` directives can be continued on subsequent lines by starting them with ``#VVT::``:

.. code-block:: python

    #VVT: directive_name : args
    #VVT:: ...
    #VVT:: ...

Which is equivalent to

.. code-block:: python

    #VVT: directive_name : args ... ...

.. raw:: html

   <font size="+3"> Available test directives:</font>

"""  # noqa: E501

from .analyze import analyze
from .copy import copy
from .depends_on import depends_on
from .devices import devices
from .enable import enable
from .keywords import keywords
from .link import link
from .parameterize import parameterize
from .preload import preload
from .processors import processors
from .set_attribute import set_attribute
from .skipif import skipif
from .sources import sources
from .testname import testname
from .timeout import timeout
from .xdiff import xdiff
from .xfail import xfail

name = testname  # noqa: F401


def all_directives():
    _all = [
        analyze,
        copy,
        depends_on,
        devices,
        enable,
        keywords,
        link,
        parameterize,
        preload,
        processors,
        set_attribute,
        skipif,
        sources,
        testname,
        timeout,
        xdiff,
        xfail,
    ]
    return _all
