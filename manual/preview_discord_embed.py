from pathlib import Path
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.discord_embed import build_job_embed_payload
from app.normalization.schemas import Language, NormalizedJob, Salary


def main() -> None:
    job = NormalizedJob(
        title="Junior Python Developer",
        company="Example Company",
        source="djinni",
        source_url="https://example.com/job/123",
        location="Poznan, Poland / Remote",
        remote_type="remote",
        seniority="junior",
        salary=Salary(min=8000, max=11000, currency="PLN", period="month"),
        required_skills=["Python", "SQL", "FastAPI"],
        optional_skills=["Docker", "Playwright"],
        languages=[Language(name="English", level="B1")],
        responsibilities=[
            "Build backend services",
            "Work with PostgreSQL data models",
        ],
        requirements=[
            "Commercial or project experience with Python",
            "Basic SQL knowledge",
        ],
        benefits=[
            "Remote work",
            "Flexible working hours",
        ],
        summary="Junior backend role focused on Python APIs and SQL-backed services.",
    )
    payload = build_job_embed_payload(job)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
