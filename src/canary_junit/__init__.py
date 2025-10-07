import canary

from .reporter import JunitReporter


@canary.hookimpl(specname="canary_session_reporter")
def junit_reporter() -> canary.CanaryReporter:
    return JunitReporter()
