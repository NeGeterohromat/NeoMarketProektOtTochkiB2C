"""
Package for NeoMarketProektOtTochkiB2C.
"""
from .celery import app as celery_app

__all__ = ('celery_app',)