from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.models import ScrapeFilters


DJINNI_JUNIOR_PYTHON = ScrapeFilters(
    source="djinni",
    search_keywords="Python",
    experience_levels="no_exp,1y",
    english_levels="pre,intermediate,upper",
    location="remote",
    include_keywords="python fastapi django sql backend",
    exclude_keywords="senior lead architect manager devops",
)


PRACA_PL_JUNIOR_PYTHON = ScrapeFilters(
    source="praca_pl",
    search_keywords="python junior",
    experience_levels="junior",
    english_levels="",
    location="warszawa",
    include_keywords="python sql backend",
    exclude_keywords="senior lead manager",
)
