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

EXPOSE 8200

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]
