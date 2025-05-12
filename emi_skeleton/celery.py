import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "emi_skeleton.settings")

app = Celery("emi_skeleton")

# This tells Celery: take every DJANGO setting that starts with CELERY_
# and strip the prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Autodiscover tasks in all installed apps
app.autodiscover_tasks()