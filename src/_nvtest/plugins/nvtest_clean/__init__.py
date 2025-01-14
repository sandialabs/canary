import nvtest


@nvtest.plugin.register(scope="main", stage="setup")
def setup_parser(parser: nvtest.Parser) -> None:
    parser.add_argument(
        "--post-clean",
        command="run",
        action="store_true",
        default=False,
        help="Clean up files created by a test if it finishes successfully [default: %(default)s]",
    )


@nvtest.plugin.register(scope="session", stage="finish")
def cleanup_test_cases(session: nvtest.Session) -> None:
    if not nvtest.config.getoption("post_clean"):
        return
    cases = session.active_cases()
    for case in cases:
        if case.status == "success":
            case.cleanup()
