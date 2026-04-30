# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "Canary SWING Presentation"
copyright = "2026, Tim Fuller"
author = "Tim Fuller"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx_revealjs",
    "sphinx_revealjs.ext.footnotes",
    "sphinx_revealjs.ext.oembed",
    "sphinxmermaid",
]
templates_path = ["_templates"]
exclude_patterns = []

mermaid_params = ["--theme", "dark"]

html_theme = "alabaster"
html_static_path = ["_static"]

revealjs_html_theme = "revealjs-simple"
revealjs_static_path = ["_static"]
# revealjs_style_theme = "dark"
revealjs_script_conf = {
    "controls": True,
    "progress": True,
    "hash": True,
    "center": False,
    "transition": "slide",
    "highlight": {"theme": "monokai"},
}
revealjs_css_files = [
    "custom.css",
    "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/monokai.min.css",
]
revealjs_script_plugins = [
    {
        "name": "RevealNotes",
        "src": "revealjs/plugin/notes/notes.js",
    },
    {
        "name": "RevealHighlight",
        "src": "revealjs/plugin/highlight/highlight.js",
    },
    {
        "name": "RevealMath",
        "src": "revealjs/plugin/math/math.js",
    },
    {
        "name": "RevealCustomControls",
        "src": "https://cdn.jsdelivr.net/npm/reveal.js-plugins@latest/customcontrols/plugin.js",
    },
]

pygments_style = "monokai"
highlight_language = "python"

rst_prolog = r"""
.. role:: pyc(code)
   :class: pyc

.. role:: pyf(code)
   :class: pyf

.. role:: py(code)
   :class: py
"""
