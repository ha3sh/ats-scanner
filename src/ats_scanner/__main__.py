"""Launcher: bind 127.0.0.1, open browser.

Entry point for the `ats` console script. Port choice and the missing-static
check are small pure helpers so they are testable without starting a server
(SPEC §2 user flow step 1).
"""

import socket
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

from ats_scanner.main import build_app

HOST = "127.0.0.1"
PREFERRED_PORT = 8000
FALLBACK_PORT = 8765


def _port_is_free(port: int) -> bool:
    """True when a TCP bind on HOST:port succeeds right now."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((HOST, port))
    except OSError:
        return False
    finally:
        sock.close()
    return True


def choose_port(preferred: int = PREFERRED_PORT, fallback: int = FALLBACK_PORT) -> int | None:
    """Return the first free port, or None when both are taken."""
    for port in (preferred, fallback):
        if _port_is_free(port):
            return port
    return None


def static_missing_message(index: Path) -> str | None:
    """None when the built frontend exists; otherwise the command to run."""
    if index.exists():
        return None
    return (
        f"{index} is missing.\n"
        "\n"
        "The built frontend is committed and served from static/. Build it first:\n"
        "\n"
        "    uv run ats-build\n"
        "\n"
        "Then run `uv run ats` again."
    )


def main() -> int:
    """Check the frontend, pick a port, open the browser, serve."""
    index = Path(__file__).parent / "static" / "index.html"
    if message := static_missing_message(index):
        print(message, file=sys.stderr)
        return 1

    port = choose_port()
    if port is None:
        print(
            f"Ports {PREFERRED_PORT} and {FALLBACK_PORT} are already in use on "
            f"{HOST}. Free one of them and run `uv run ats` again.",
            file=sys.stderr,
        )
        return 1

    url = f"http://{HOST}:{port}/"
    print(f"Serving at {url} (press Ctrl+C to stop)")
    # The page should already exist when the tab opens, so brief delay.
    threading.Timer(1.5, webbrowser.open, [url]).start()
    uvicorn.run(build_app(), host=HOST, port=port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
