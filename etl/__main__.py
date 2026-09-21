"""
Entrypoint for `python -m etl`
"""
import sys
from etl.cli import main

if __name__ == "__main__":
    sys.exit(main())
