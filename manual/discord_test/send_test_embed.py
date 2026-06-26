from pathlib import Path
import argparse
import json
import os
import sys

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.discord_embed import build_job_embed_payload


DISCORD_API_BASE = "https://discord.com/api/v10"


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a test Discord job embed.")
    parser.add_argument(
        "--sample",
        default=str(Path(__file__).with_name("sample_job.json")),
        help="Path to normalized job JSON.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print payload without sending it to Discord.",
    )
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")

    payload = build_job_embed_payload(_load_sample(args.sample))
    if args.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    bot_token = _required_env("DISCORD_BOT_TOKEN")
    channel_id = _required_env("DISCORD_CHANNEL_ID")
    message = send_discord_message(
        bot_token=bot_token,
        channel_id=channel_id,
        payload=payload,
    )
    print(f"Discord test message sent: id={message.get('id')}")


def send_discord_message(
    *,
    bot_token: str,
    channel_id: str,
    payload: dict,
) -> dict:
    response = requests.post(
        f"{DISCORD_API_BASE}/channels/{channel_id}/messages",
        headers={
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=20,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            "Discord API request failed: "
            f"status={response.status_code} body={response.text}"
        )
    return response.json()


def _load_sample(path: str) -> dict:
    with Path(path).open(encoding="utf-8") as file:
        return json.load(file)


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required .env value: {name}")
    return value


if __name__ == "__main__":
    main()
