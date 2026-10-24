"""WSGI entry point: `gunicorn wsgi:app` or `flask --app wsgi <command>`."""

from app import create_app

app = create_app()
