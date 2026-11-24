# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=app:app manage.py ./
COPY --chown=app:app config ./config
COPY --chown=app:app recruitment ./recruitment
COPY --chown=app:app templates ./templates
COPY --chown=app:app docker ./docker

COPY vendor/age.js vendor/age.js.sha256 /tmp/vendor/
RUN cd /tmp/vendor \
    && sha256sum -c age.js.sha256 \
    && cp age.js /app/recruitment/static/recruitment/age.js \
    && chmod +x /app/docker/entrypoint.sh \
    && chown -R app:app /app


# Store the standalone Tailwind binary outside root-owned site-packages.
ENV TAILWINDCSS_BIN_DIR=/app/.tailwindcss

RUN mkdir -p "$TAILWINDCSS_BIN_DIR" \
    && chown app:app "$TAILWINDCSS_BIN_DIR"

USER app

# Build-only placeholder settings. No database connection is needed here.
RUN DJANGO_SECRET_KEY=build-only-not-runtime \
    POSTGRES_PASSWORD=build-only-not-runtime \
    python manage.py tailwind init \
      --no-input --app-name theme --tailwind-version 4s

# Add project source scanning and accessible base styling to the
# generated Tailwind v4 stylesheet.
RUN python - <<'PY'
from pathlib import Path

path = Path("theme/static_src/src/styles.css")
with path.open("a") as f:
    f.write("""
@source "../../../recruitment";
@source "../../../templates";

@layer base {
  button, input, select, textarea {
    @apply border border-slate-600 rounded px-3 py-2 my-2;
  }
  button {
    @apply bg-slate-900 text-white;
  }
  button:disabled {
    @apply opacity-60;
  }
  :focus-visible {
    @apply outline outline-2 outline-offset-2 outline-blue-700;
  }
  label {
    @apply block font-medium;
  }
  fieldset, article {
    @apply border border-slate-400 rounded p-4 my-4;
  }
  textarea {
    @apply w-full;
  }
  dd {
    @apply mb-3 whitespace-pre-wrap break-words;
  }
  a {
    @apply underline;
  }
}
""")
PY

RUN DJANGO_SECRET_KEY=build-only-not-runtime \
    POSTGRES_PASSWORD=build-only-not-runtime \
    python manage.py tailwind install

RUN DJANGO_SECRET_KEY=build-only-not-runtime \
    POSTGRES_PASSWORD=build-only-not-runtime \
    python manage.py tailwind build

# Initial scaffolding only. Commit migrations before production rather
# than regenerating them on every image build.
RUN DJANGO_SECRET_KEY=build-only-not-runtime \
    POSTGRES_PASSWORD=build-only-not-runtime \
    python manage.py makemigrations recruitment

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]

CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", \
     "--timeout", "60", \
     "--error-logfile", "-"]
