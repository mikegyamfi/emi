
# Django Deployment & Hosting Guide (Production-Ready)

## 1. Project Setup
```bash
sudo apt update && sudo apt install -y python3 python3-pip python3-venv postgresql libpq-dev nginx
git clone <your-repo-url>
cd <your-project-name>
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 2. Environment Configuration
```bash
cp .env.example .env
```
Fill `.env` with:
```
DJANGO_SECRET_KEY=your-very-secret-key
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DATABASE_URL=postgres://user:password@localhost:5432/dbname
ARKESEL_API_KEY=your-arkesel-key
DEBUG=False
REDIS_URL=redis://127.0.0.1:6379/0
```

## 3. Migrate & Static Files
```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

## 4. PostgreSQL Setup
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo -u postgres psql
```
Inside psql:
```
CREATE DATABASE yourdbname;
CREATE USER yourdbuser WITH PASSWORD 'yourpassword';
ALTER ROLE yourdbuser SET client_encoding TO 'utf8';
ALTER ROLE yourdbuser SET default_transaction_isolation TO 'read committed';
ALTER ROLE yourdbuser SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE yourdbname TO yourdbuser;
\q
```

## Run Migration
```bash
python manage.py makemigrations
python manage.py migrate
```

## Superuser Creation
```bash
python manage.py createsuperuser
```


## 5. Gunicorn
```bash
pip install gunicorn
gunicorn your_project.wsgi:application --bind 0.0.0.0:8000
```

Create `/etc/systemd/system/gunicorn.service`:
```ini
[Unit]
Description=gunicorn daemon
After=network.target

[Service]
User=youruser
Group=www-data
WorkingDirectory=/home/youruser/your_project
ExecStart=/home/youruser/your_project/venv/bin/gunicorn your_project.wsgi:application --bind 127.0.0.1:8000 --workers 3

[Install]
WantedBy=multi-user.target
```

## 6. Nginx
```bash
sudo apt install nginx
```

Create `/etc/nginx/sites-available/your_project`:
```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location = /favicon.ico { access_log off; log_not_found off; }
    location /static/ {
        root /home/youruser/your_project;
    }

    location / {
        include proxy_params;
        proxy_pass http://127.0.0.1:8000;
        proxy_redirect off;
    }

    location /static/ {
        alias /path/to/your/project/static/;
    }

    location /media/ {
        alias /path/to/your/project/media/;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/your_project /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## 7. Celery (Required)
```bash
sudo apt install redis-server
sudo systemctl enable redis

pip install celery redis
```

`your_project/celery.py`:
```python
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'your_project.settings')
app = Celery('your_project')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
```

Add in `__init__.py`:
```python
from .celery import app as celery_app
__all__ = ('celery_app',)
```

Create `/etc/systemd/system/celery.service`:
```ini
[Unit]
Description=Celery Service
After=network.target

[Service]
Type=forking
User=youruser
WorkingDirectory=/home/youruser/your_project
ExecStart=/home/youruser/your_project/venv/bin/celery -A your_project multi start worker --loglevel=info --logfile=/var/log/celery.log
ExecStop=/home/youruser/your_project/venv/bin/celery multi stopwait worker
ExecReload=/home/youruser/your_project/venv/bin/celery -A your_project multi restart worker --loglevel=info --logfile=/var/log/celery.log

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reexec
sudo systemctl start celery
sudo systemctl enable celery
```

## 8. Security
```bash
DEBUG = False
ALLOWED_HOSTS = ['yourdomain.com']
```

Enable HTTPS:
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

## 9. Final Checks
- Gunicorn → `systemctl status gunicorn`
- Nginx → `systemctl status nginx`
- Celery → `systemctl status celery`
- Redis connected

## 10. Logs & Management
```bash
sudo systemctl restart gunicorn
sudo systemctl restart celery
sudo systemctl restart nginx

journalctl -u gunicorn -f
journalctl -u celery -f
```

