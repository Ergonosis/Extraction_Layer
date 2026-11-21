"""Run the schema command, then terminate its proxy so the Job can finish."""

import subprocess
from urllib.request import Request, urlopen


def main() -> int:
    code = 1
    try:
        code = subprocess.run(['flask', 'db', 'upgrade'], check=False).returncode
    finally:
        # The admin server is localhost-only and enabled only in Job containers.
        with urlopen(Request('http://127.0.0.1:9091/quitquitquit', method='POST'), timeout=10):
            pass
    return code


if __name__ == '__main__':
    raise SystemExit(main())
