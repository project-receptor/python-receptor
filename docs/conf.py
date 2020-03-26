# -*- coding: utf-8 -*-

import os
import sys

sys.path.insert(0, os.path.abspath("../"))
sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("./"))

project = "Receptor"
copyright = "2019, Red Hat"
author = "Red Hat"

version = ""
release = "1.0.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.todo",
    "sphinx.ext.coverage",
    "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]

source_suffix = [".rst", ".md"]

master_doc = "index"

language = None

exclude_patterns = []

pygments_style = "sphinx"

html_theme = "alabaster"

html_static_path = ["_static"]

htmlhelp_basename = "Receptordoc"

latex_elements = {}

latex_documents = [
    (master_doc, "Receptor.tex", "Receptor Documentation", "Red Hat", "manual",),
]

man_pages = [(master_doc, "receptor", "Receptor Documentation", [author], 1)]

texinfo_documents = [
    (
        master_doc,
        "Receptor",
        "Receptor Documentation",
        author,
        "Receptor",
        "One line description of project.",
        "Miscellaneous",
    ),
]

todo_include_todos = True
