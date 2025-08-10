# Releasing a New Version

This document outlines the process for publishing a new version of `switchbot-actions` to PyPI.

The project uses a two-stage release process that leverages GitHub Actions and PyPI's Trusted Publishers feature for secure, token-less deployments.

## Step 1: Pre-release on TestPyPI

Before publishing to the official PyPI registry, it is crucial to verify the package on TestPyPI. This ensures that the package builds correctly and that its metadata is rendered properly.

1.  **Update Version**: Bump the version number in `pyproject.toml`.

2.  **Create and Push a Git Tag**: Create a new Git tag that matches the version in `pyproject.toml`, prefixed with `v`. For example, for version `0.2.0`, create the tag `v0.2.0`.

    ```bash
    git tag v0.2.0
    git push origin v0.2.0
    ```

3.  **Verify on TestPyPI**: Pushing the tag will automatically trigger the `publish-to-testpypi.yml` workflow. Once the action completes, verify the new version on TestPyPI:
    - Check the project page: [https://test.pypi.org/p/switchbot-actions](https://test.pypi.org/p/switchbot-actions)
    - Install the package from TestPyPI to confirm it works as expected:
      ```bash
      pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple switchbot-actions
      ```

## Step 2: Release on PyPI

Once the package has been verified on TestPyPI, you can proceed with the official release.

1.  **Create a New GitHub Release**: Go to the [Releases page](https://github.com/hnw/switchbot-actions/releases) on GitHub and click "Draft a new release".

2.  **Choose the Tag**: Select the tag you just pushed (e.g., `v0.2.0`).

3.  **Generate Release Notes**: Click "Generate release notes" to automatically populate the description with recent pull requests.

4.  **Publish Release**: Click "Publish release". This will trigger the `publish-to-pypi.yml` workflow, which builds and publishes the package to the official PyPI registry.

5.  **Verify on PyPI**: Once the action completes, verify the new version on PyPI:
    - Check the project page: [https://pypi.org/p/switchbot-actions](https://pypi.org/p/switchbot-actions)
    - Install the package from PyPI:
      ```bash
      pip install switchbot-actions
      ```
