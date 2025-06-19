# pymsi

[![PyPI](https://img.shields.io/pypi/v/python-msi)](https://pypi.org/project/python-msi/)
[![MIT License](https://img.shields.io/pypi/l/python-msi.svg)](https://github.com/nightlark/pymsi/blob/main/LICENSE)
[![Python Versions](https://img.shields.io/pypi/pyversions/python-msi.svg)](https://pypi.org/project/python-msi/)
[![CI](https://github.com/nightlark/pymsi/actions/workflows/ci.yml/badge.svg)](https://github.com/nightlark/pymsi/actions)
[![Documentation Status](https://readthedocs.org/projects/pymsi/badge/?version=latest)](https://pymsi.readthedocs.io/en/latest/?badge=latest)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/nightlark/pymsi/main.svg)](https://results.pre-commit.ci/latest/github/nightlark/pymsi/main)

A pure Python library for reading and manipulating Windows Installer (MSI) files. Based on the rust msi crate and msitools utilities.

## Getting Started

For a demo of what pymsi can do, check out the [online MSI viewer and file extractor](https://pymsi.readthedocs.io/en/latest/msi_viewer.html) on our ReadTheDocs site. It's like lessmsi, but runs fully client-side in your browser.

For more in-depth documentation on pymsi usage and the API, see the [documentation](https://pymsi.readthedocs.io/en/latest/) (very early WIP).

### Installation

pymsi is available on PyPI (PEP 541 request for pymsi name is being processed):

```sh
pip install python-msi
```

It is recommended to either install it in a virtual environment, or use a tool such as pipx or uv to avoid potential conflicts with other Python modules on the same system.

### Usage

To use pymsi as a library that gets called from other code:

```python
import pymsi
```

To use pymsi as a command line tool:

```bash
pymsi <command> [path_to_msi_file] [output_folder]
```

Use the help command to see a list of supported commands:

```bash
Available commands:
  tables - List all tables in the MSI file
  dump - Dump the contents of the MSI file
  test - Check if the file is a valid MSI file
  extract - Extract files from the MSI file
  help - Show this help message
```

## Getting Involved

For questions or support, please create a new discussion on [GitHub Discussions](https://github.com/nightlark/pymsi/discussions/categories/q-a),
or [open an issue](https://github.com/nightlark/pymsi/issues/new/choose) for bug reports and feature requests.

## Contributing

Contributions are welcome. Bug fixes or minor changes are preferred via a
pull request to the [pymsi GitHub repository](https://github.com/nightlark/pymsi).
For more information on contributing see the [CONTRIBUTING](./CONTRIBUTING.md) file.

## License

pymsi is released under the MIT license. See the [LICENSE](./LICENSE)
and [NOTICE](./NOTICE) files for details. All new contributions must be made
under this license.

SPDX-License-Identifier: MIT

LLNL-CODE-862419
