import pytest

from safety import validate_test_target


def pytest_configure(config):
    # Collection is read-only; execution must prove it uses the loopback-only
    # synthetic database, isolated server and file-based email sink.
    if not config.option.collectonly:
        try:
            validate_test_target()
        except RuntimeError as exc:
            raise pytest.UsageError(str(exc)) from exc
