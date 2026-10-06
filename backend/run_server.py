"""Local single-process backend launcher supporting Playwright subprocesses on Windows."""
import os
from pathlib import Path

import uvicorn


def main():
    # Keep SQLite/storage paths stable regardless of the shell's current directory.
    os.chdir(Path(__file__).resolve().parent)
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000,
                reload=False, workers=1, loop="asyncio", proxy_headers=False)


if __name__ == "__main__":
    main()
