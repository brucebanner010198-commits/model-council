"""Sphinx configuration for The Council documentation."""

project = "The Council"
author = "The Council Team"
copyright = "2026, The Council"
release = "1.0.0"
version = "1.0"

# -- General configuration ---------------------------------------------------
extensions = [
    "myst_parser",
    "sphinx_copybutton",
    "sphinx_design",
    "sphinxcontrib.httpdomain",
]

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "linkify",
    "substitution",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Disable smartquotes so we never auto-convert -- to en/em dashes or
# straight quotes to curly ones in the rendered HTML.
smartquotes = False

# -- HTML output -------------------------------------------------------------
html_theme = "furo"
html_title = "The Council"
html_static_path = ["_static"]

html_theme_options = {
    "sidebar_hide_name": False,
    "navigation_with_keys": True,
    "light_css_variables": {
        "color-brand-primary": "#0f766e",
        "color-brand-content": "#0f766e",
    },
    "dark_css_variables": {
        "color-brand-primary": "#34d399",
        "color-brand-content": "#34d399",
        "color-background-primary": "#0a0a0c",
    },
    "footer_icons": [],
}

# Group the two audiences clearly in the sidebar.
html_sidebars = {}
