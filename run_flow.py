from pathlib import Path

from app.flow import save_example_vacancy, send_example_vacancy


def main() -> None:
    example_path = Path("example.txt")
    print(save_example_vacancy(example_path))

    should_send = input("Send to Telegram? [y/N]: ").strip().lower()
    if should_send == "y":
        result = send_example_vacancy(example_path)
        print("Telegram API response:", result.get("ok"))


if __name__ == "__main__":
    main()
