"""Tests for the ats-build / ats-dev helpers (no npm runs here)."""

from ats_scanner.tooling import build_steps, dev_steps, missing_node_message


def test_build_steps_are_npm_ci_then_npm_build() -> None:
    assert build_steps(r"C:\Program Files\nodejs\npm.cmd") == [
        [r"C:\Program Files\nodejs\npm.cmd", "ci"],
        [r"C:\Program Files\nodejs\npm.cmd", "run", "build"],
    ]


def test_dev_steps_are_npm_run_dev() -> None:
    assert dev_steps("npm") == ["npm", "run", "dev"]


def test_missing_node_message_is_none_when_npm_exists() -> None:
    assert missing_node_message(r"C:\Program Files\nodejs\npm.cmd") is None


def test_missing_node_message_explains_what_to_install() -> None:
    message = missing_node_message(None)
    assert message is not None
    assert "Node.js" in message
    assert "nodejs.org" in message
