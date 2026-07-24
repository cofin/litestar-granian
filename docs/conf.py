from litestar_granian.__metadata__ import __version__

project = "Litestar Granian"
copyright = "2023-2026, Cody Fincher"
author = "Cody Fincher"
version = __version__
release = __version__

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.autosectionlabel",
    "sphinx.ext.githubpages",
    "sphinx.ext.intersphinx",
    "sphinx_copybutton",
    "sphinx_click",
    "sphinx_design",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "click": ("https://click.palletsprojects.com/en/stable/", None),
    "litestar": ("https://docs.litestar.dev/latest/", None),
}

nitpicky = True
nitpick_ignore: list[tuple[str, str]] = []

napoleon_google_docstring = True
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_attr_annotations = True

autoclass_content = "class"
autodoc_class_signature = "separated"
autodoc_member_order = "bysource"
autodoc_typehints_format = "short"
autodoc_type_aliases = {
    "LogStyle": "Literal['auto', 'native', 'standard', 'json']",
    "StaticMode": "Literal['off', 'auto']",
}
autosectionlabel_prefix_document = True

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "shibuya"
html_static_path = ["_static"]
html_css_files = ["style.css"]
html_favicon = "_static/favicon.png"
html_logo = "_static/logo-icon.svg"
html_show_sourcelink = False
html_title = "Litestar Granian"
html_context = {
    "source_type": "github",
    "source_user": "cofin",
    "source_repo": "litestar-granian",
    "source_version": "main",
}
html_theme_options = {
    "accent_color": "amber",
    "navigation_with_keys": True,
    "page_layout": "default",
    "nav_links": [
        {"title": "Quickstart", "url": "getting-started/quickstart"},
        {
            "title": "Guides",
            "url": "guides/configuration",
            "children": [
                {"title": "Configuration", "url": "guides/configuration"},
                {"title": "Logging and metrics", "url": "guides/logging-and-metrics"},
                {"title": "Static files", "url": "guides/static-files"},
                {"title": "Deployment", "url": "guides/deployment"},
            ],
        },
        {"title": "Reference", "url": "reference/index"},
        {
            "title": "GitHub",
            "url": "https://github.com/cofin/litestar-granian",
            "external": True,
        },
    ],
}
