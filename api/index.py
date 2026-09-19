import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")

from myproject.wsgi import application

