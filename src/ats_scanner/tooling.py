"""Development tooling: the `ats-build` and `ats-dev` console scripts.

Node is needed only to build the frontend, never to run the app. The command
lists and the missing-Node message are pure helpers so they can be tested
without launching npm (tests never run npm).
"""

import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import uvicorn

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WEB_DIR = REPO_ROOT / "web"

HOST = "127.0.0.1"
PORT = 8000

_MISSING_NODE_MESSAGE = (
    "Node.js and npm are required to build the frontend, and neither was "
    "found on PATH.\n"
    "\n"
    "Install Node.js 22.12 or newer from https://nodejs.org and run "
    "`uv run ats-build` again."
)


def find_npm() -> str | None:
    """Return the npm executable on PATH, or None when Node is not installed."""
    for name in ("npm", "npm.cmd"):
        found = shutil.which(name)
        if found is not None:
            return found
    return None


def build_steps(npm: str) -> list[list[str]]:
    """The commands `ats-build` runs, in order: a clean install, then a build."""
    return [[npm, "ci"], [npm, "run", "build"]]


def dev_steps(npm: str) -> list[str]:
    """The frontend half of the development loop."""
    return [npm, "run", "dev"]


def missing_node_message(npm: str | None) -> str | None:
    """None when npm is available; otherwise the message to print."""
    if npm is not None:
        return None
    return _MISSING_NODE_MESSAGE


def _run(commands: Sequence[Sequence[str]]) -> int:
    for command in commands:
        printable = " ".join(command)
        print(f"$ {printable}", flush=True)
        result = subprocess.run(list(command), cwd=WEB_DIR, check=False)
        if result.returncode != 0:
            print(
                f"Command failed with exit code {result.returncode}: {printable}", file=sys.stderr
            )
            return result.returncode
    return 0


def main() -> int:
    """`ats-build`: install locked frontend dependencies, then build to static/."""
    npm = find_npm()
    if message := missing_node_message(npm):
        print(message, file=sys.stderr)
        return 1
    assert npm is not None
    return _run(build_steps(npm))


def dev_main() -> int:
    """`ats-dev`: run the API with reload; the Vite dev server is the other half."""
    npm = find_npm() or "npm"
    print(
        "Starting the API with reload on "
        f"http://{HOST}:{PORT} (press Ctrl+C to stop).\n"
        "In a second terminal, start the frontend dev server:\n"
        f"\n    {' '.join(dev_steps(npm))}\n",
        flush=True,
    )
    uvicorn.run(
        "ats_scanner.api:create_app",
        factory=True,
        host=HOST,
        port=PORT,
        reload=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
