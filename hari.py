#!/usr/bin/env python3
"""
Hari - Productivity assistant service.

  python hari.py run    Start the web API and services
"""

import sys


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__.strip())
        sys.exit(0)

    cmd = sys.argv[1].lower()
    if cmd == "run":
        import hari_services
        sys.argv = [sys.argv[0]]
        hari_services.main()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__.strip())
        sys.exit(1)


if __name__ == "__main__":
    main()
