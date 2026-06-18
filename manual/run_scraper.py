from pathlib import Path
import argparse
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.flow import scrape_and_save


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a scraper manually.")
    parser.add_argument("source", nargs="?", default="djinni", choices=["djinni", "praca_pl"])
    args = parser.parse_args()

    vacancies = scrape_and_save(source=args.source, pause_before_close=True)

    print(f"Saved vacancies: {len(vacancies)}")
    for vacancy in vacancies:
        print(f"- {vacancy.title} | {vacancy.url}")


if __name__ == "__main__":
    main()
