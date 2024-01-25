import glob
import os
from typing import TYPE_CHECKING

from .. import config
from ..reporters import Reporter
from ..reporters import cdash
from ..reporters import html
from ..reporters import markdown
from ..session import Session
from ..util import tty

if TYPE_CHECKING:
    from argparse import Namespace

    from ..config.argparsing import Parser


description = "Generate test reports"


def setup_parser(parser: "Parser") -> None:
    parent = parser.add_subparsers(dest="parent_command", metavar="")
    cdash_parser = parent.add_parser("cdash", help="Generate and post CDash XML")
    sp = cdash_parser.add_subparsers(dest="child_command", metavar="")
    p = sp.add_parser("create", help="Create CDash XML files")
    p.add_argument(
        "--build",
        dest="buildname",
        metavar="name",
        help="The name of the build that will be reported to CDash.",
    )
    p.add_argument(
        "--site",
        metavar="name",
        help="The site name that will be reported to CDash. "
        "[default: current system hostname]",
    )
    p.add_argument(
        "-f",
        metavar="file",
        help="Read site, build, and buildstamp from this XML "
        "file (eg, Build.xml or Configure.xml)",
    )
    p.add_argument(
        "-d",
        metavar="directory",
        help="Write reports to this directory [default: $session/_reports/cdash]",
    )
    group = p.add_mutually_exclusive_group()
    group.add_argument(
        "--track",
        metavar="track",
        help="Results will be reported to this group on CDash [default: Experimental]",
    )
    group.add_argument(
        "--build-stamp",
        dest="buildstamp",
        metavar="stamp",
        help="Instead of letting the CDash reporter prepare the buildstamp which, "
        "when combined with build name, site and project, uniquely identifies the "
        "build, provide this argument to identify the build yourself. "
        "Format: %%Y%%m%%d-%%H%%M-<track>",
    )

    p = sp.add_parser("post", help="Post CDash XML files")
    p.add_argument(
        "--project",
        required=True,
        metavar="project",
        help="The CDash project",
    )
    p.add_argument(
        "--url",
        metavar="url",
        required=True,
        help="The base CDash url (do not include project)",
    )
    p.add_argument("files", nargs="*", help="XML files to post")

    p = sp.add_parser("create-gitlab-issues")
    p.add_argument(
        "--project",
        required=True,
        metavar="project",
        help="The CDash project",
    )
    p.add_argument(
        "--url",
        required=True,
        help="The base CDash url (do not include project)",
    )
    parser.add_argument(
        "--gitlab-url",
        default=os.getenv("CI_PROJECT_URL"),
        help="The GitLab project url [default: %(default)s]",
    )
    parser.add_argument(
        "--gitlab-project-id",
        default=os.getenv("CI_PROJECT_ID"),
        help="The GitLab project's ID [default: %(default)s]",
    )
    for var in ("GITLAB_ACCESS_TOKEN", "ACCESS_TOKEN"):
        if var in os.environ:
            default_access_token = os.environ[var]
            break
    else:
        default_access_token = None
    parser.add_argument(
        "-a",
        dest="access_token",
        default=default_access_token,
        help="The GitLab read/write API access token [default: %(default)s]",
    )
    parser.add_argument("-d", "--date", help="Date to retrieve from CDash")
    parser.add_argument(
        "-f",
        "--filtergroups",
        action="append",
        help="Groups to pull down from CDash [default: Latest]",
    )
    parser.add_argument(
        "--skip-site",
        default=None,
        dest="skip_sites",
        action="append",
        metavar="site",
        help="Sites to skip (accepts Python regular expression) [default: %(default)s]",
    )

    p = sp.add_parser("summary", help="Create HTML summary of CDash site")
    p.add_argument(
        "--url",
        required=True,
        metavar="url",
        help="CDash URL",
    )
    p.add_argument(
        "--project",
        required=True,
        metavar="project",
        help="The name of the CDash project",
    )
    p.add_argument(
        "-t",
        action="append",
        metavar="track",
        dest="build_groups",
        help="CDash build track to fetch",
    )
    p.add_argument(
        "-s",
        "--skip",
        action="append",
        metavar="site",
        dest="skip_sites",
        help="Skip builds from these sites",
    )
    p.add_argument(
        "-m",
        action="append",
        metavar="email",
        dest="mailto",
        help="mail report to these addresses",
    )
    p.add_argument(
        "-o",
        dest="file",
        metavar="file",
        help="write report to this file",
    )

    html_parser = parent.add_parser("html", help="Generate HTML reports")
    sp = html_parser.add_subparsers(dest="child_command", metavar="")
    p = sp.add_parser("create", help="Create local HTML report files")

    md_parser = parent.add_parser("markdown", help="Generate markdown reports")
    sp = md_parser.add_subparsers(dest="child_command", metavar="")
    p = sp.add_parser("create", help="Create local markdown report files")


def report(args: "Namespace") -> int:
    command = (args.parent_command, args.child_command)
    if command == ("cdash", "summary"):
        cdash.cdash_summary(
            url=args.url,
            project=args.project,
            buildgroups=args.build_groups,
            mailto=args.mailto,
            skip_sites=args.skip_sites,
            file=args.file,
        )
        return 0
    elif command == ("cdash", "post") and args.files:
        cdash.Reporter.post(args.url, args.project, *args.files)
        return 0
    elif command == ("cdash", "create-gitlab-issues"):
        if args.access_token is None:
            tty.die("gitlab access token required")
        if args.gitlab_url is None:
            tty.die("gitlab project url required")
        if args.gitlab_project is None:
            tty.die("gitlab project required")
        if args.gitlab_project_id is None:
            tty.die("gitlab project id required")
        cdash.create_issues_from_failed_tests(
            access_token=str(args.access_token),
            cdash_url=str(args.url),
            cdash_project=str(args.project),
            gitlab_url=str(args.gitlab_url),
            gitlab_project_id=int(str(args.gitlab_project_id)),
            date=args.date,
            filtergroups=args.filtergroups,
            skip_sites=args.skip_sites,
        )
        return 0
    if not config.get("session:work_tree"):
        tty.die("not a nvtest session (or any of the parent directories): .nvtest")
    session = Session.load(mode="r")
    reporter: Reporter
    if args.parent_command == "cdash":
        reporter = cdash.Reporter(session, dest=args.d)
        if args.child_command == "create":
            if args.f:
                opts = dict(
                    buildstamp=args.buildstamp,
                    track=args.track,
                    buildname=args.buildname,
                )
                if any(list(opts.values())):
                    s = ", ".join(list(opts.keys()))
                    raise ValueError(f"-f {args.f!r} incompatible with {s}")
                reporter.read_site_info(args.f, namespace=args)
            reporter.create(
                args.buildname,
                site=args.site,
                track=args.track,
                buildstamp=args.buildstamp,
            )
        elif args.child_command == "post":
            if not args.files:
                args.files = glob.glob(os.path.join(reporter.xml_dir, "*.xml"))
            if not args.files:
                tty.die("nvtest report cdash post: no xml files to post")
            reporter.post(args.url, args.project, *args.files)
        else:
            tty.die(f"{args.child_command}: unknown `nvtest report cdash` subcommand")
        return 0
    elif args.parent_command == "html":
        reporter = html.Reporter(session)
        if args.child_command == "create":
            reporter.create()
        else:
            tty.die(f"{args.child_command}: unknown `nvtest report html` subcommand")
        return 0
    elif args.parent_command == "markdown":
        reporter = markdown.Reporter(session)
        if args.child_command == "create":
            reporter.create()
        else:
            tty.die(
                f"{args.child_command}: unknown `nvtest report markdown` subcommand"
            )
        return 0
    else:
        tty.die(f"{args.parent_command}: unknown subcommand")
    return 1
