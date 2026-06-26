from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.models import ScrapeFilters


ALL_SOURCES_JUNIOR_PYTHON = ScrapeFilters(
    source="all",
    search_keywords="Python",
    experience_levels="no_exp,1y",
    english_levels="pre,intermediate,upper",
    location="remote poznan",
    include_keywords="python fastapi django sql backend",
    exclude_keywords="senior lead architect manager devops",
)


DJINNI_JUNIOR_PYTHON = ALL_SOURCES_JUNIOR_PYTHON.model_copy(
    update={"source": "djinni"}
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
