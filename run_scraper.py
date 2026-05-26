from app.flow import scrape_and_save_djinni


def main() -> None:
    vacancies = scrape_and_save_djinni(limit=10)

    print(f"Saved vacancies: {len(vacancies)}")
    for vacancy in vacancies:
        print(f"- {vacancy.title} | {vacancy.url}")


if __name__ == "__main__":
    main()
