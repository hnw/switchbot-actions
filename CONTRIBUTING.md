# Contributing to switchbot-actions

First off, thank you for considering contributing to this project! We welcome all contributions, from bug reports to new features.

To ensure a smooth process for everyone, please take a moment to review these guidelines.

## **Development Setup**

To get started with development, please follow these steps to set up your local environment.

### 1. Prerequisites

This project uses Poetry for dependency management. Before you begin, please ensure you have Poetry installed on your system.

The recommended way to install Poetry is using **`pipx`**, which installs it in an isolated environment to prevent conflicts.

```bash
pipx install poetry
```

If you don't have `pipx`, you can install it with `pip install pipx`. For all other installation methods, please refer to [the official Poetry installation guide](https://python-poetry.org/docs/#installation).

### **2. Clone the Repository**

Clone the project to your local machine.

```bash
git clone https://github.com/hnw/switchbot-actions.git
cd switchbot-actions
```

### **3. Install Dependencies**

Now, install the project dependencies using a single Poetry command. This command will automatically create a virtual environment and install all necessary packages (both for production and development) listed in `poetry.lock`.

```bash
poetry install
```

### **4. Set Up pre-commit Hooks**

This project uses `pre-commit` to automatically run code quality checks. To set up the hooks, run:

```bash
pre-commit install
```

You are now all set up for development\! To activate the virtual environment created by Poetry and run commands, you can use `poetry shell`.

```bash
# Activate the virtual environment
eval $(poetry env activate)

# You will now see that you are inside the project's environment
# (.venv) $
```

---

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
    - Use a clear and descriptive title.
    - In the description, explain the problem you are solving and the changes you have made.
    - If your PR addresses an existing issue, please link to it in the description (e.g., `Fixes #123`).

We will review your pull request as soon as possible. Thank you for your contribution!
