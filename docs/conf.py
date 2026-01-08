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

extensions = ["myst_parser", "sphinx_copybutton", "sphinxext.opengraph"]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "furo"
html_theme_options = {
    # This adds a "Edit this page" / "View source" link to the top right
    "source_repository": "https://github.com/nightlark/pymsi/",
    "source_branch": "main",
    "source_directory": "docs/",
    "sidebar_hide_name": True,
}
html_title = "pymsi"
html_logo = "./logos/pymsi_logo_with_text_transparent_600px_lossy.webp"
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

ogp_site_url = "https://pymsi.readthedocs.io/"
ogp_image = "https://pymsi.readthedocs.io/en/latest/_static/pymsi_social_preview.jpg"
ogp_description_length = 200

# -- External Example Files Download -----------------------------------------
# List of entries to download into _static/ directory during build.
# Example: ["https://example.com/file1.msi", ["https://site.org/file2.zip", "custom_name.zip", "Friendly Name"]]
EXTERNAL_EXAMPLES = [
    ["https://www.7-zip.org/a/7z2501-x64.msi", "7z2501-x64.msi", "7-Zip 25.01 (2MB)"],
    #    Uncertain about license for this one, so leaving it out for now.
    #    ["https://github.com/user-attachments/files/20845219/Orca.zip", "Orca.zip", "Orca"],
    [
        "https://github.com/mgeeky/msidump/raw/refs/heads/main/test-cases/sample4-customaction-run-calc.msi.bin",
        "sample4-customaction-run-calc.msi",
        '"Malicious" Run calc Custom Action Example from msidump (32KB)',
    ],
    [
        "https://github.com/microsoft/PowerToys/releases/download/v0.21.1/PowerToysSetup-0.21.1-x64.msi",
        "PowerToysSetup-0.21.1-x64.msi",
        "PowerToys v0.21.1 (20MB)",
    ],
    [
        "https://the.earth.li/~sgtatham/putty/latest/wa64/putty-arm64-0.83-installer.msi",
        "putty-arm64-0.83-installer.msi",
        "PuTTY 0.83 64-bit Arm (3.1MB)",
    ],
]


def download_external_files(app):
    """Downloads external example files and generates an index JSON."""
    import json
    import os
    import urllib.request
    from urllib.parse import urlparse

    static_dir = os.path.join(app.confdir, "_static")
    os.makedirs(static_dir, exist_ok=True)

    # Start with the default local example if it exists
    available_examples = []
    local_example = os.path.join(static_dir, "example.msi")
    if os.path.exists(local_example):
        available_examples.append(
            {
                "name": "Basic Example (12KB)",
                "filename": "example.msi",
                "url": "_static/example.msi",
            }
        )

    if EXTERNAL_EXAMPLES:
        print(f"[pymsi] Processing {len(EXTERNAL_EXAMPLES)} external example files...")

        for entry in EXTERNAL_EXAMPLES:
            if isinstance(entry, (list, tuple)):
                url, filename, name = entry
            else:
                url = entry
                filename = os.path.basename(urlparse(url).path)
                name = filename

            destination = os.path.join(static_dir, filename)
            success = False

            # Skip if file already exists to preserve bandwidth
            if os.path.exists(destination):
                print(f"[pymsi]   Skipping {filename} (already exists)")
                success = True
            else:
                try:
                    print(f"[pymsi]   Downloading {url} -> {filename} ...")
                    headers = {"User-Agent": "Mozilla/5.0 (compatible; pymsi-docs/1.0)"}
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req) as response, open(
                        destination, "wb"
                    ) as out_file:
                        out_file.write(response.read())
                    success = True
                except Exception as e:
                    print(f"[pymsi]   ERROR: Failed to download {url}: {e}")

            if success:
                available_examples.append(
                    {"name": name, "filename": filename, "url": f"_static/{filename}"}
                )

    # Generate the index file for the frontend
    index_path = os.path.join(static_dir, "examples.json")
    try:
        with open(index_path, "w") as f:
            json.dump(available_examples, f, indent=2)
        print(f"[pymsi] Generated examples index at {index_path} ({len(available_examples)} files)")
    except Exception as e:
        print(f"[pymsi] ERROR generating examples index: {e}")


def setup(app):
    app.connect("builder-inited", download_external_files)
