# syntax=docker/dockerfile:1.4

ARG PYTHON_VERSION=3.13-slim
FROM python:${PYTHON_VERSION} AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    python3-dev

WORKDIR /app

RUN pip install --no-cache-dir build

ARG TARGETPLATFORM
ENV BUILD_PLATFORM=${TARGETPLATFORM}

COPY requirements.txt ./

COPY --chmod=755 .docker/build-wheels.sh .docker/

RUN .docker/build-wheels.sh deps

COPY . .

# Declare APP_VERSION and IS_PRERELEASE arguments
ARG APP_VERSION
ARG IS_PRERELEASE

RUN .docker/build-wheels.sh project "${APP_VERSION}" "${IS_PRERELEASE}"

FROM python:${PYTHON_VERSION} AS final

WORKDIR /app

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

COPY --from=builder /app/dist/wheels /wheels/

ENV PYTHONUSERBASE=/home/appuser/.local
ENV PATH="${PYTHONUSERBASE}/bin:${PATH}"

RUN mkdir -p ${PYTHONUSERBASE} \
    && chown -R appuser:appgroup ${PYTHONUSERBASE} /wheels \
    && su -s /bin/sh -c "pip install --no-cache-dir --user --no-index --find-links=/wheels switchbot-actions" appuser \
    && rm -rf /wheels

USER appuser

ENTRYPOINT ["python", "-m", "switchbot_actions.cli"]
