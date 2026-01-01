# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "pymsi"
# pylint: disable-next=redefined-builtin
copyright = "2026, Lawrence Livermore National Security"
author = "Ryan Mast"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = ["myst_parser", "sphinx_copybutton"]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "furo"
html_theme_options = {
    "description": "pymsi",
    # This adds a "Edit this page" / "View source" link to the top right
    "source_repository": "https://github.com/nightlark/pymsi/",
    "source_branch": "main",
    "source_directory": "docs/",
}
# html_logo = "./logos/pymsi-logo.png"
# html_favicon = html_logo
html_sidebars = {
    "**": [
        "sidebar/brand.html",
        "sidebar/search.html",
        "sidebar/scroll-start.html",
        "sidebar/navigation.html",
        "sidebar/ethical-ads.html",
        "sidebar/scroll-end.html",
        "github-star.html",
        "sidebar/variant-selector.html",
    ]
}
html_static_path = ["_static"]
