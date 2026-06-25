from pathlib import Path
import argparse
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import reset_tables


def main() -> None:
    parser = argparse.ArgumentParser(description="Drop and recreate all ORM tables.")
    parser.add_argument("--yes", action="store_true", help="Confirm destructive reset.")
    args = parser.parse_args()

    if not args.yes:
        raise SystemExit("Refusing to reset database without --yes")

    reset_tables()
    print("Database tables were dropped and recreated.")


if __name__ == "__main__":
    main()
