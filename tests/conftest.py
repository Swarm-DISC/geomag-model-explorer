"""Every test that drives the app in headless Chromium is marked ``browser`` (RULES §5), so the
quick loop (``pytest -m 'not browser'``) stays seconds long instead of a multi-minute WebGL run."""
import pytest

BROWSER_FILES = {"test_browser.py", "test_webgl_probe.py"}


def pytest_collection_modifyitems(items):
    for item in items:
        if item.path.name in BROWSER_FILES or item.path.name.endswith("_browser.py"):
            item.add_marker(pytest.mark.browser)
