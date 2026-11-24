#!/bin/sh
set -eu

python manage.py collectstatic --noinput --verbosity 0

exec "$@"
