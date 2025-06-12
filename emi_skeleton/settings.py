# settings.py

from pathlib import Path
from decouple import config, Csv
from datetime import timedelta

# ──────────────────────────────────────────────
# BASE & SECURITY
# ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config("DJANGO_SECRET_KEY")
DEBUG = config("DEBUG", cast=bool, default=False)

ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    cast=Csv(),
    default="localhost,127.0.0.1",
)

# ──────────────────────────────────────────────
# INSTALLED APPS & MIDDLEWARE
# ──────────────────────────────────────────────
INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework_simplejwt.token_blacklist',
    'drf_spectacular',
    'corsheaders',
    # your apps…
    'account',
    'cart_management',
    'checkout_processing',
    'business',
    'core',
    'document_manager',
    'product_service_management',
    'market_intelligence',
    'feedback',
    'forum',
]

MIDDLEWARE = [
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'emi_skeleton.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'account/templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'emi_skeleton.wsgi.application'

# ──────────────────────────────────────────────
# DATABASES
# ──────────────────────────────────────────────
if DEBUG:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DATABASE_NAME'),
            'USER': config('DATABASE_USER'),
            'PASSWORD': config('DATABASE_PASSWORD'),
            'HOST': config('DATABASE_HOST', default='localhost'),
            'PORT': config('DATABASE_PORT', default='5432'),
        }
    }

# ──────────────────────────────────────────────
# AUTH & REST FRAMEWORK
# ──────────────────────────────────────────────
AUTH_USER_MODEL = 'account.CustomUser'

AUTHENTICATION_BACKENDS = [
    "account.backends.PhoneOrEmailBackend",
    "django.contrib.auth.backends.ModelBackend",
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication"
    ],
    "EXCEPTION_HANDLER": "account.exceptions.custom_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "20/min",
        "user": "100/min",
        "resend_activation": "5/min",
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=720),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=3),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "EMI Accounts API",
    "DESCRIPTION": "Authentication, feedback, and user‐profile endpoints",
    "VERSION": "v1",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SWAGGER_UI_SETTINGS": {"persistAuthorization": True},
    "SECURITY": [{"BearerAuth": []}],
    "COMPONENTS": {
        "securitySchemes": {
            "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
        }
    },
}

# ──────────────────────────────────────────────
# CORS
# ──────────────────────────────────────────────
CORS_ALLOW_ALL_ORIGINS = config("CORS_ALLOW_ALL_ORIGINS", cast=bool, default=True)
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = ["*"]
CORS_ALLOW_METHODS = ["DELETE", "GET", "OPTIONS", "PATCH", "POST", "PUT"]

# ──────────────────────────────────────────────
# INTERNATIONALIZATION
# ──────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ──────────────────────────────────────────────
# STATIC & MEDIA
# ──────────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'assets'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ──────────────────────────────────────────────
# EMAIL
# ──────────────────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_HOST_USER = config("SMTP_USERNAME")
EMAIL_HOST_PASSWORD = config("SMTP_PASSWORD")
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

EMAIL_OTP_EXPIRY_MINUTES = config("EMAIL_OTP_EXPIRY_MINUTES", default=10)

# ──────────────────────────────────────────────
# CELERY
# ──────────────────────────────────────────────
CELERY_BROKER_URL = config("REDIS_URL", default="redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL

# ──────────────────────────────────────────────
# PRODUCTION‐ONLY SECURITY
# ──────────────────────────────────────────────
if not DEBUG:
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# ──────────────────────────────────────────────
# (Optional) AWS S3
# ──────────────────────────────────────────────
# INSTALLED_APPS += ['storages']
# AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID')
# AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY')
# AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')
# AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='us-east-1')
# STATICFILES_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
# DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
# AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
# STATIC_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/static/'
# MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/media/'
