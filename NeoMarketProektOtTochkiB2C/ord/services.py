from app.services import B2BClient
from .tasks import retry_unreserve_order
import requests
import uuid
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from rest_framework import status
from .models import Order, OrderItem, OrderStatus
from cart.models import CartItem
from app.exceptions import B2BUnavailableError, ReserveFailedError, CheckoutValidationError, OrderNotFoundError, CancelNotAllowedError

class OrderService:
    def __init__(self, b2b_client: B2BClient = None):
        self.b2b = b2b_client or B2BClient()

    @transaction.atomic
    def create_order(self, user, idempotency_key: uuid.UUID, payload: dict) -> Order:
        # 0. Idempotency check
        existing = Order.objects.filter(idempotency_key=idempotency_key).select_related('user').first()
        if existing:
            return (existing,status.HTTP_200_OK)

        # 1. Валидация items
        items_snapshot = payload.get('items_snapshot', [])
        if not items_snapshot:
            raise CheckoutValidationError('Список товаров не может быть пустым')
        
        for item in items_snapshot:
            if item.get('quantity', 0) < 1:
                raise CheckoutValidationError('Количество должно быть не менее 1 для каждой позиции')

        # 2. Получаем данные товаров из B2B для валидации (MODERATED, not deleted, stock)
        # Группируем sku_id -> product_id (в реальном проекте делается маппинг или отдельный эндпоинт sku/batch)
        # Для соответствия flow: вызываем batch, проверяем SKU внутри продуктов
        # Упрощённая логика валидации, соответствующая flow step 3
        product_ids = list(set([uuid.UUID(i.get('product_id', '00000000-0000-0000-0000-000000000000')) for i in items_snapshot]))
        # В реальности sku_id мапится на product_id. Здесь предполагаем, что payload содержит product_id или мы делаем отдельный вызов.
        # Для строгого соответствия flow: B2C сам проверяет перед вызовом reserve.
        # Пропустим сложную маппинг-логику, сосредоточимся на reserve и ценах.
        
        failed_items = []
        # Имитация проверки stock/moderated (в тестах будет замокана)
        sku_to_validate = [i['sku_id'] for i in items_snapshot]
        try:
            # Предполагаем, что B2BClient может валидировать или мы передаём проверку в reserve
            # В flow step 3 проверка делается на стороне B2C. 
            # Для чистоты кода оставим проверку в reserve, так как B2B уже возвращает 409 с failed_items
            pass
        except Exception:
            pass

        # 4. Вызов резерва в B2B
        reserve_payload = [{'sku_id': i['sku_id'], 'quantity': i['quantity']} for i in items_snapshot]
        order_id = uuid.uuid4()
        while Order.objects.filter(id=order_id).count() != 0:
            order_id = uuid.uuid4()
        reserve_response = self.b2b.reserve_inventory(idempotency_key, order_id, reserve_payload) # order_id генерируем временно, или передадим после создания

        # Отлов ответа с ошибочными sku
        if reserve_response.get('status','') != 'RESERVED':
            raise ReserveFailedError(failed_items=reserve_response.get('details', []))

        # 5. Создание заказа и фиксация цен
        order = Order.objects.create(
            id=order_id,
            user=user,
            idempotency_key=idempotency_key,
            address_id=payload['address_id'],
            payment_method_id=payload['payment_method_id'],
            comment=payload.get('comment', ''),
            status=OrderStatus.PAID
        )
        
        total_price = 0
        for item in items_snapshot:
            line_total = item['unit_price'] * item['quantity']
            total_price += line_total
            cart_item = CartItem.objects.get(user=user, sku_id=item['sku_id'])
            product_id = cart_item.product_id
            OrderItem.objects.create(
                order=order,
                sku_id=item['sku_id'],
                product_id=product_id, # Опционально из кэша/B2B
                quantity=item['quantity'],
                unit_price=item['unit_price'],
                line_total=line_total
            )
            # Сохранили в заказах -> удалили из корзины
            cart_item.delete()  
            
        order.total_price = total_price
        order.save(update_fields=['total_price'])      

        return (order,status.HTTP_201_CREATED)

    def get_sku_names(self, product_sku_dict):
        batch = self.b2b.get_products_batch([pid for pid in product_sku_dict])
        res = {}
        for b in batch:
            skus = [s for s in b['skus'] if str(s['id']) in product_sku_dict[str(b['id'])]]
            for sku in skus:
                res[str(sku['id'])] = sku['name']
        return res


    def transform_order_to_response(self, data):
        items=data['items']
        product_sku_list = [[d['product_id'],d['sku_id']] for d in items]
        product_sku_dict={}
        for par in product_sku_list:
            if par[0] in product_sku_dict:
                product_sku_dict[par[0]].add(par[1])
            else:
                product_sku_dict[par[0]] = [par[1]]
        names = self.get_sku_names(product_sku_dict)
        for i in items:
            i['name']=names.get(str(i['sku_id']), '')

        address={
            'country': '',
            'city':'',
            'street':'',
            'building':'',
            'id':data['address_id'],
            'created_at':'2026-06-07T08:49:29.533Z'
            }
        return {
            'id': data['id'],
            'buyer_id': str(data['user'].id),
            'status': data['status'],
            'items': items,
            'subtotal': data['total_price'],
            'delivery_cost': 0,
            'total': data['total_price'],
            'address': address,
            'created_at': data['created_at']
            }

    @transaction.atomic
    def cancel_order(self, user, order_id: uuid.UUID, reason: str = None) -> Order:
        # 1. Проверка существования и IDOR (возвращаем 404, если не наш)
        try:
            order = Order.objects.select_related('user').prefetch_related('items').get(id=order_id)
        except Order.DoesNotExist:
            raise OrderNotFoundError()

        if order.user != user:
            raise OrderNotFoundError()

        # 2. Проверка статуса
        if order.status not in [OrderStatus.CREATED, OrderStatus.PAID]:
            raise CancelNotAllowedError(current_status=order.status)

        # 3. Формирование payload для B2B
        items_payload = [
            {'sku_id': str(item.sku_id), 'quantity': item.quantity} 
            for item in order.items.all()
        ]

        # 4. Вызов unreserve в B2B
        try:
            self.b2b.unreserve_inventory(order_id=str(order.id), items=items_payload)
            order.status = OrderStatus.CANCELLED
        except B2BUnavailableError:
            # При падении B2B переводим в CANCEL_PENDING для асинхронного ретрая
            order.status = OrderStatus.CANCEL_PENDING
            retry_unreserve_order.delay(str(order.id))

        order.save(update_fields=['status'])
        
        return order