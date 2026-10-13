"""Build public documentation without importing Django or connecting to a database."""

import tomllib
from pathlib import Path

metadata = tomllib.loads(
    (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text()
)["project"]
project = "Django QBE 2"
author = "Carlos A. Rocha"
copyright = "2026, Carlos A. Rocha"
release = metadata["version"]
language = "en"
extensions = []
exclude_patterns = []
html_theme = "alabaster"
html_title = f"{project} documentation"
html_theme_options = {
    "description": "Authorized reports for Django",
    "github_user": "CARocha",
    "github_repo": "django-qbe2",
    "github_button": False,
    "fixed_sidebar": True,
    "page_width": "1100px",
    "body_max_width": "850px",
}
html_sidebars = {"**": ["about.html", "navigation.html", "searchfield.html"]}
html_show_sourcelink = True
