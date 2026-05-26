from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.flow import scrape_and_save_djinni


def main() -> None:
    vacancies = scrape_and_save_djinni()

    print(f"Saved vacancies: {len(vacancies)}")
    for vacancy in vacancies:
        print(f"- {vacancy.title} | {vacancy.url}")


if __name__ == "__main__":
    main()
