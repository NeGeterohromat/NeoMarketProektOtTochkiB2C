import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'NeoMarketProektOtTochkiB2C.settings')
app = Celery('neomarket_b2c')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks(['ord']) # Важно: добавь 'ord' в список приложений для автообнаружения задач
