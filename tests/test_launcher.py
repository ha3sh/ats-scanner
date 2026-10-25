"""Tests for the launcher's pure helpers: port choice and missing static."""

import socket
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ats_scanner.__main__ import choose_port, static_missing_message


def _free_port() -> int:
    """Ask the OS for a currently free TCP port on 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def _held(port: int) -> Iterator[None]:
    """Hold a TCP port open on 127.0.0.1, as a running server would."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        yield
    finally:
        sock.close()


def test_uses_preferred_port_when_free() -> None:
    preferred = _free_port()
    fallback = _free_port()
    assert choose_port(preferred=preferred, fallback=fallback) == preferred


def test_falls_back_when_preferred_is_taken() -> None:
    preferred = _free_port()
    fallback = _free_port()
    with _held(preferred):
        assert choose_port(preferred=preferred, fallback=fallback) == fallback


def test_returns_none_when_both_ports_are_taken() -> None:
    preferred = _free_port()
    fallback = _free_port()
    with _held(preferred), _held(fallback):
        assert choose_port(preferred=preferred, fallback=fallback) is None


def test_missing_static_message_points_to_the_build_command(
    tmp_path: Path,
) -> None:
    message = static_missing_message(tmp_path / "index.html")
    assert message is not None
    assert "uv run ats-build" in message
    assert "uv run ats" in message


def test_no_message_when_static_index_exists(tmp_path: Path) -> None:
    index = tmp_path / "index.html"
    index.write_text("frontend not built yet", encoding="utf-8")
    assert static_missing_message(index) is None
