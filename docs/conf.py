# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys

# Add project to path for autodoc
sys.path.insert(0, os.path.abspath(".."))

# Setup Django before importing models
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "example.project.settings")
import django
django.setup()

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "Omniman"
copyright = "2025, Omniman Contributors"
author = "Omniman Contributors"
release = "0.5.9"
version = "0.5"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",           # Auto-document code
    "sphinx.ext.napoleon",          # Google/NumPy docstrings
    "sphinx.ext.intersphinx",       # Links to Django docs
    "sphinx.ext.viewcode",          # Links to source code
    "sphinx.ext.todo",              # TODOs
    "sphinx_copybutton",            # Copy button in code blocks
    "sphinxcontrib.httpdomain",     # REST API docs
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "*.md"]

# The master toctree document
master_doc = "index"

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "furo"
html_static_path = ["_static"]
html_css_files = ["custom.css"]

html_theme_options = {
    "sidebar_hide_name": False,
    "navigation_with_keys": True,
    "top_of_page_button": "edit",
    "source_repository": "https://github.com/your-org/omniman",
    "source_branch": "main",
    "source_directory": "docs/",
}

html_title = "Omniman Documentation"
html_short_title = "Omniman"

# -- Options for autodoc -----------------------------------------------------

autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
    "member-order": "bysource",
}

autodoc_typehints = "description"
autodoc_class_signature = "separated"

# -- Options for intersphinx -------------------------------------------------

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "django": (
        "https://docs.djangoproject.com/en/5.0/",
        "https://docs.djangoproject.com/en/5.0/objects.inv",
    ),
}

# -- Options for Napoleon (Google-style docstrings) --------------------------

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_type_aliases = None

# -- Options for TODO extension ----------------------------------------------

todo_include_todos = True
