SYSTEM_PROMPT = """Return only JSON.
Do not add data that is not present in the input text.
Use null when information is missing.
Use [] when a list is empty.
Do not change the vacancy URL.
Separate required and optional requirements.
Extract required_skills, optional_skills, languages, responsibilities, requirements, and benefits from the description when they are present.
Do not put the whole description into summary. Summary must be 1-2 concise sentences.
Keep each list item short and useful. Prefer concrete technologies, tools, duties, and requirements over generic marketing text.
If the vacancy mentions several offices or countries, keep them in location.
If the vacancy is remote but also lists offices, set remote_type to remote or hybrid from the text and keep the office locations in location.
Do not treat remote_type as a replacement for location.
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

Return all keys from the schema. If the input contains bullet lists or section text, convert them into the matching arrays.

Input:
{input_text}
"""
