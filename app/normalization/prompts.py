SYSTEM_PROMPT = """Return only JSON.
Do not add data that is not present in the input text.
Use null when information is missing.
Use [] when a list is empty.
Do not change the vacancy URL.
Separate required and optional requirements.
"""

USER_PROMPT_TEMPLATE = """Normalize this job vacancy into the exact JSON shape below.

Schema example:
{
  "title": "Junior Python Developer",
  "company": "Example Company",
  "source": "pracuj",
  "source_url": "https://example.com/job/123",
  "location": "Poznan",
  "remote_type": "hybrid",
  "seniority": "junior",
  "salary": {
    "min": 8000,
    "max": 11000,
    "currency": "PLN",
    "period": "month"
  },
  "required_skills": ["Python", "SQL"],
  "optional_skills": ["Docker"],
  "languages": [
    {
      "name": "English",
      "level": "B1"
    }
  ],
  "responsibilities": [],
  "requirements": [],
  "benefits": [],
  "summary": "Short vacancy summary"
}

Input:
{input_text}
"""
