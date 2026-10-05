FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# L'environnement est dans l'image : on le lance directement. `uv run` voudrait écrire son
# cache sous $HOME, impossible avec une racine en lecture seule (le pod ne démarrait pas).
ENV PATH="/app/.venv/bin:$PATH"

COPY app/ app/
COPY data/ data/

# Convention ADR-0004 MirAI next, alignée sur Dockerflow : l'image porte son journal en
# /app/version.json, servi sur /__version__ (et repris par /health). Les valeurs viennent du
# build (build-args) ; un build de poste donne « dev ».
ARG VERSION=dev
ARG COMMIT=
ARG BUILD=
ARG CODE_DATE=
ARG SOURCE=
COPY scripts/version_json.py CHANGELOG.md* /tmp/version/
RUN python /tmp/version/version_json.py --version "$VERSION" --commit "$COMMIT" --build "$BUILD" \
      --code-date "$CODE_DATE" --source "$SOURCE" --changelog /tmp/version/CHANGELOG.md \
      --out /app/version.json \
 && chmod 0644 /app/version.json \
 && rm -rf /tmp/version

EXPOSE 8200

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]
