# syntax=docker/dockerfile:1.4
ARG PYTHON_VERSION=3.13-slim
FROM python:${PYTHON_VERSION} AS builder

# uv の導入
COPY --from=ghcr.io/astral-sh/uv:0.9.18 /uv /bin/

WORKDIR /app

RUN uv venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY requirements.txt ./

RUN uv pip install -r requirements.txt

COPY . .

ARG APP_VERSION
ARG IS_PRERELEASE

RUN if [ -n "${APP_VERSION}" ]; then \
      EXTRA_ARGS=""; \
      if [ "${IS_PRERELEASE}" = "true" ]; then \
        EXTRA_ARGS="--index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple --index-strategy unsafe-best-match"; \
      fi; \
      # PyPI (TestPyPI) からインストール
      uv pip install ${EXTRA_ARGS} "switchbot-actions==${APP_VERSION}"; \
    else \
      # ローカルソースからビルドしてインストール
      uv pip install .; \
    fi

# Final Stage
FROM python:${PYTHON_VERSION} AS final

WORKDIR /app

# ユーザー作成
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# Builderで作った venv をそのままコピー
COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv

# venv にパスを通す
ENV PATH="/app/.venv/bin:$PATH"

USER appuser

ENTRYPOINT ["python", "-m", "switchbot_actions.cli"]
