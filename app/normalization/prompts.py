SYSTEM_PROMPT = """Return only JSON.
Do not add data that is not present in the input text.
Use null when information is missing.
Use [] when a list is empty.
Do not change the vacancy URL.
Separate required and optional requirements.
Extract required_skills, optional_skills, languages, responsibilities, requirements, and benefits from the description when they are present.
Do not reduce requirements to only technology names. Preserve years of experience, degree requirements, certifications, language levels, and other qualifiers.
If the input has headings like "What are we looking for?", "Requirements", "Candidate profile", or similar, put the complete bullet items under requirements.
Extract languages from both CEFR levels (A1-C2) and words like pre-intermediate, intermediate, upper-intermediate, advanced, fluent, native.
Do not put the whole description into summary. Summary must be 1-2 concise sentences.
Keep skill lists focused on concrete technologies/tools, but keep requirements/responsibilities/benefits as complete useful bullet items from the vacancy text.
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
Requirements must keep important details, for example "1+ years of commercial experience with Python", not just "Python".

Input:
{input_text}
"""
