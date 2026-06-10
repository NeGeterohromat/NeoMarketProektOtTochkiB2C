from celery import shared_task
from django.db import transaction

from .models import Order, OrderStatus
from app.services import B2BClient
from app.exceptions import B2BUnavailableError

@shared_task(
    bind=True,
    autoretry_for=(B2BUnavailableError,),
    retry_backoff=True,       # Экспоненциальная задержка (2с, 4с, 8с, 16с...)
    retry_backoff_max=600,    # Максимальная задержка 10 минут
    retry_kwargs={'max_retries': 10},
    retry_jitter=True         # Добавляет случайность, чтобы избежать "thundering herd" при восстановлении B2B
)
def retry_unreserve_order(self, order_id: str):
    """
    Асинхронная задача для снятия резерва при отмене заказа.
    Вызывается при переходе заказа в CANCEL_PENDING.
    """
    try:
        with transaction.atomic():
            # Блокируем строку для обновления, чтобы избежать гонок состояний
            order = Order.objects.select_for_update().get(id=order_id)
            
            # Защита от повторной обработки, если статус уже изменился
            if order.status == OrderStatus.CANCELLED:
                return
            
            if order.status != OrderStatus.CANCEL_PENDING:
                return

            b2b_client = B2BClient()
            items_payload = [
                {'sku_id': str(item.sku_id), 'quantity': item.quantity} 
                for item in order.items.all()
            ]

            # Вызов unreserve в B2B. При ошибке B2BUnavailableError Celery автоматически сделает retry.
            b2b_client.unreserve_inventory(order_id=str(order.id), items=items_payload)
            
            # Если код дошел сюда, значит B2B ответил успешно
            order.status = OrderStatus.CANCELLED
            order.save(update_fields=['status'])

    except Order.DoesNotExist:
        pass
        # Не ретраим, если заказа физически нет
    except B2BUnavailableError as e:
        raise e  # Передаем исключение дальше, чтобы сработал механизм autoretry_for
    except Exception as e:
        # Для непредвиденных ошибок также можно использовать retry, но с осторожностью
        raise self.retry(exc=e)
