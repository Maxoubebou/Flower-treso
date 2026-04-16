"""
local_settings.py — Paramètres de développement local (SQLite).
Importer ce fichier via DJANGO_SETTINGS_MODULE ou l'append en fin de settings.py.
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
