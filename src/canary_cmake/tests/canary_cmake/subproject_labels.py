# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import subprocess
import sys
import xml.dom.minidom as xml

from _canary.util.filesystem import mkdirp
from _canary.util.filesystem import working_dir


def test_cdash_labels_for_subproject(tmpdir):
    """Test the plugin 'canary_cdash_labels_for_subproject'

    The canary_cdash_labels_for_subproject allows adding subproject labels for the entire test
    session
    """
    with working_dir(tmpdir.strpath, create=True):
        setup_cdash_labels_for_subproject()
        run_the_thing_and_check()


def test_cdash_subproject_label(tmpdir):
    """Test the plugin 'canary_cdash_subroject_label'

    This plugin allows tests to define their CDash subproject label.  If the subproject label is
    not included in the test case's keywords, it is added

    """
    with working_dir(tmpdir.strpath, create=True):
        setup_cdash_subproject_label()
        run_the_thing_and_check()


def run_the_thing_and_check():
    env = dict(os.environ)
    env["PYTHONPATH"] = os.getcwd()
    env.pop("CANARYCFG64", None)
    env["CANARY_DISABLE_KB"] = "1"
    subprocess.run([f"{sys.prefix}/bin/canary", "-p", "baz", "run", "."], env=env)
    subprocess.run(
        [f"{sys.prefix}/bin/canary", "-d", "-p", "baz", "report", "cdash", "create"],
        env=env,
    )
    file = "TestResults/CDASH/Test-0.xml"
    doc = xml.parse(open(file))
    names = get_subproject_labels(doc)
    assert sorted(names) == ["baz", "foo"]
    names = get_test_labels(doc)
    assert sorted(names) == ["baz", "foo"]


def setup_cdash_labels_for_subproject():
    mkdirp("baz")
    with open("baz/__init__.py", "w") as fh:
        fh.write("""\
import canary
@canary.hookimpl
def canary_cdash_labels_for_subproject():
    return ['foo', 'baz']
""")
    with open("baz.pyt", "w") as fh:
        fh.write("""\
import sys
import canary
canary.directives.keywords('baz')
def test():
    return 0
if __name__ == '__main__':
    sys.exit(test())
""")
    with open("foo.pyt", "w") as fh:
        fh.write("""\
import sys
import canary
canary.directives.keywords('foo')
def test():
    return 0
if __name__ == '__main__':
    sys.exit(test())
""")


def setup_cdash_subproject_label():
    """Test the plugin 'canary_cdash_subroject_label'

    This plugin allows tests to define their CDash subproject label.  If the subproject label is
    not included in the test case's keywords, it is added

    """
    mkdirp("baz")
    with open("baz/__init__.py", "w") as fh:
        fh.write("""\
import canary
@canary.hookimpl
def canary_cdash_subproject_label(case):
    return case.spec.family
""")
    with open("baz.pyt", "w") as fh:
        fh.write("""\
import sys
import canary
def test():
    return 0
if __name__ == '__main__':
    sys.exit(test())
""")
    with open("foo.pyt", "w") as fh:
        fh.write("""\
import sys
import canary
def test():
    return 0
if __name__ == '__main__':
    sys.exit(test())
""")


def get_test_labels(doc):
    names = []
    for el1 in doc.getElementsByTagName("Testing"):
        for el2 in el1.getElementsByTagName("Test"):
            for el3 in el2.getElementsByTagName("Labels"):
                for el4 in el3.getElementsByTagName("Label"):
                    names.append(el4.childNodes[0].nodeValue)
    return names


def get_subproject_labels(doc):
    return [el.getAttribute("name") for el in doc.getElementsByTagName("Subproject")]
