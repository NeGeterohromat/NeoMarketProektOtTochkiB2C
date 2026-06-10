"""
Package for NeoMarketProektOtTochkiB2C.
"""
try:
    from .celery import app as celery_app
    __all__ = ('celery_app',)
except Exception as e:
    # Если Celery не настроен или не установлен — пропускаем инициализацию
    # Тесты и Django будут работать без Celery
    import logging
    logging.getLogger(__name__).warning(f"Celery initialization skipped: {e}")
    celery_app = None
    __all__ = ()