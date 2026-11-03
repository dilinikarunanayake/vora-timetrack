#!/usr/bin/env bash
# Runs on the hosting company's servers each time you deploy.
# exit on the first error, so a failed step stops the deploy.
set -o errexit

pip install -r requirements.txt

# Copy all CSS, JS and images into staticfiles/ (with fingerprinted names).
python manage.py collectstatic --no-input

# Apply any new database migrations.
python manage.py migrate --no-input
