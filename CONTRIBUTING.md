# Contributing to pymsi

Thank you for considering contributing to our project! We appreciate your help.

## Reporting Issues

1. If you find a bug or have a feature request, please [open a new issue](https://github.com/nightlark/pymsi/issues) and provide detailed information about the problem.
2. If you find security issues or vulnerabilities, please [report here](https://github.com/nightlark/pymsi/security)

## Making Contributions

We welcome contributions from the community. To contribute to this project, follow these steps:

1. Fork the repository on GitHub.
2. Clone your forked repository to your local machine.

All contributions to pymsi are made under the MIT license (MIT).

### For Developers:

1. Create a virtual environment with python >= 3.8 [Optional, but recommended]

```bash
python -m venv venv
source venv/bin/activate
```

2. Clone pymsi

```bash
git clone git@github.com:nightlark/pymsi.git
```

3. Create an editable pymsi install (changes to code will take effect immediately):

```bash
pip install -e .
```

To install optional dependencies required for running pytest and pre-commit:

```bash
pip install -e ".[test,dev]"
```

## Code of Conduct

All participants in the pymsi community are expected to follow our [Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct.html).
