#!/bin/sh
set -e

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT="${SCRIPT_DIR}/.."
WHEELS_DIR="${PROJECT_ROOT}/dist/wheels"

retry_command() {
    MAX_RETRIES=6
    RETRY_DELAY=10
    RETRY_COUNT=0

    until "$@"; do
        RETRY_COUNT=$((RETRY_COUNT + 1))
        if [ ${RETRY_COUNT} -ge ${MAX_RETRIES} ]; then
            echo "::error::Command failed after ${MAX_RETRIES} attempts: $@"
            exit 1
        fi
        echo "Command failed. Retrying in ${RETRY_DELAY} seconds... (${RETRY_COUNT}/${MAX_RETRIES})"
        sleep ${RETRY_DELAY}
    done
}

STAGE="${1}"

mkdir -p "${WHEELS_DIR}"

echo "Starting wheel build process..."
echo "Output directory: ${WHEELS_DIR}"


if [ "${BUILD_PLATFORM}" = "linux/arm/v6" ]; then
    echo "linux/arm/v6 platform detected. Forcing build from source."
    PIP_WHEEL_EXTRA_ARGS="--no-binary aiohttp,cryptography,frozenlist,multidict,propcache,yarl,dbus-fast,cffi,pydantic_core,ruamel.yaml.clib"
fi

if [ "${STAGE}" = "deps" ]; then
    echo "--- Building dependency wheels ---"
    pip wheel ${PIP_WHEEL_EXTRA_ARGS} --wheel-dir="${WHEELS_DIR}" -r "${PROJECT_ROOT}/requirements.txt"

elif [ "${STAGE}" = "project" ]; then
    APP_VERSION="${2}"
    IS_PRERELEASE="${3}"

    if [ -z "${APP_VERSION}" ]; then
        echo "Building wheels from local source...";
        pip wheel ${PIP_WHEEL_EXTRA_ARGS} --wheel-dir="${WHEELS_DIR}" .
    else
        PIP_DOWNLOAD_ARGS=""
        if [ "${IS_PRERELEASE}" = "true" ]; then
            echo "Pre-release detected. Using TestPyPI as index."
            PIP_DOWNLOAD_ARGS="--index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple"
        else
            echo "Stable release detected. Using PyPI."
        fi
        echo "Downloading switchbot-actions==${APP_VERSION} wheel from PyPI..."
        retry_command pip download --dest "${WHEELS_DIR}" "switchbot-actions==${APP_VERSION}" --no-deps ${PIP_DOWNLOAD_ARGS}
    fi
else
    echo "::error:: Invalid stage '${STAGE}'. Must be 'deps' or 'project'."
    exit 1
fi

echo "Wheel build process completed successfully."
