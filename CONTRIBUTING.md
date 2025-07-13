# Contributing to switchbot-actions

First off, thank you for considering contributing to this project\! We welcome all contributions, from bug reports to new features.

To ensure a smooth process for everyone, please take a moment to review these guidelines.

-----

## Development Setup

To get started with development, please follow these steps to set up your local environment.

### 1\. Clone the Repository

Clone the project to your local machine.

```bash
git clone https://github.com/hnw/switchbot-actions.git
cd switchbot-actions
```

### 2\. Create and Activate a Virtual Environment

It is strongly recommended to use a virtual environment to avoid conflicts with other projects or your system's Python installation.

```bash
# Create a virtual environment named .venv
python3 -m venv .venv

# Activate the virtual environment
# On macOS and Linux:
source .venv/bin/activate

# On Windows:
# .venv\Scripts\activate
```

Once activated, you will see the name of the virtual environment (e.g., `(.venv)`) at the beginning of your shell prompt.

### 3\. Install Dependencies

Now, install the package in "editable" mode along with all development dependencies into the activated virtual environment.

```bash
pip install -e '.[dev]'
```

### 4\. Set Up pre-commit Hooks

Finally, install the pre-commit hooks, which will run checks automatically before each commit.

```bash
pre-commit install
```

You are now all set up for development. Your environment is isolated, and any packages you install will not affect your global Python installation.

-----

## Contribution Guidelines

### Discuss Your Changes First

For significant changes, such as adding a new feature or a large refactoring, please **open an issue first** to discuss your proposal. This helps ensure that your contribution aligns with the project's goals and avoids duplicated or unnecessary work.

For small bug fixes, you can submit a pull request directly.

### Submitting a Pull Request

When you are ready to submit your changes, please follow these steps:

1.  **Create a Branch**: Fork the repository and create a new branch from `main` for your changes. A good branch name is descriptive, like `feature/add-new-trigger` or `fix/resolve-issue-123`.

2.  **Add Tests**: Your contribution **must** be accompanied by corresponding tests. Any new feature or bug fix needs to be tested to ensure it works as expected and to prevent future regressions.

3.  **Update Documentation**: If your changes affect user-facing behavior, add new configuration options, or alter the program's logic, please update the relevant documentation (e.g., `README.md`, `config.yaml.example`).

4.  **Ensure CI Checks Pass**: All code must pass our CI checks, which include running tests and linting with `ruff`. The `pre-commit` hooks you installed will help you catch most issues locally before you push.

5.  **Write a Clear Pull Request**:

      * Use a clear and descriptive title.
      * In the description, explain the problem you are solving and the changes you have made.
      * If your PR addresses an existing issue, please link to it in the description (e.g., `Fixes #123`).

We will review your pull request as soon as possible. Thank you for your contribution\!
