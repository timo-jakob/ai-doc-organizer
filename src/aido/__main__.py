"""`python -m aido` dispatches to either the CLI or the daemon entrypoint.

python -m aido init ...           → CLI (Task 24)
python -m aido status ...         → CLI
python -m aido rebuild-index ...  → CLI
python -m aido run [--config ...] → daemon + web (this task)
"""

from __future__ import annotations

import sys


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] == "run":
        from aido.main import main as daemon_main

        return daemon_main(argv[1:])
    from aido.cli import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":
    sys.exit(main())
