import requests
import uuid
from django.conf import settings
from django.db import transaction
from app.exceptions import B2BUnavailableError, BlockedProductError
from app.services import B2BClient

# --- Cart Service ---
class CartService:

    b2b_client = B2BClient()

    @staticmethod
    def _get_identity(request):
        user = request.user if request.user.is_authenticated else None
        session_id = None
        if not user:
            session_id = request.headers.get('X-Session-Id')
            if not session_id:
                raise ValueError("X-Session-Id header is required for guest users")
        return user, session_id

    @classmethod
    def get_cart(cls, request):
        from .models import CartItem
        user, session_id = cls._get_identity(request)
        
        if user:
            items = list(CartItem.objects.filter(user=user))
        else:
            items = list(CartItem.objects.filter(session_id=session_id))
            
        # Собираем уникальные product_id для одного batch-запроса
        product_ids = list(set(str(item.product_id) for item in items if item.product_id))
        
        sku_info_map = {}
        if product_ids:
            url = f'{cls.b2b_client.base_url}/api/v1/public/products/batch'
            try:
                # b2b.yaml: возвращает массив (list) ProductPublicResponse
                products_data = cls.b2b_client._call_b2b(url,params={}, data={'product_ids': product_ids}, method='POST')
                
                for product in products_data:
                    product_id = str(product['id'])
                    status = product.get('status')
                    is_product_available = (status == 'MODERATED')
                    
                    for sku in product.get('skus', []):
                        sku_id = str(sku['id'])
                        active_qty = sku.get('active_quantity', 0)
                        
                        is_available = is_product_available and (active_qty > 0)
                        reason = None
                        
                        if not is_available:
                            if not is_product_available:
                                if status in ['BLOCKED', 'HARD_BLOCKED']:
                                    reason = 'PRODUCT_BLOCKED'
                                elif status == 'ON_MODERATION':
                                    reason = 'ON_MODERATION'
                                else:
                                    reason = 'PRODUCT_DELETED'
                            elif active_qty == 0:
                                reason = 'OUT_OF_STOCK'
                                
                        sku_info_map[sku_id] = {
                            'product_id': product_id,
                            'name': sku.get('name', 'Неизвестный товар'),
                            'price': sku.get('price', 0),
                            'available_quantity': active_qty,
                            'is_available': is_available,
                            'unavailable_reason': reason
                        }
            except B2BUnavailableError:
                raise  # Пробрасываем 503, как требует edge case #4

        cart_items_response = []
        subtotal = 0
        items_count = 0
        unavailable_count = 0

        for item in items:
            sku_id_str = str(item.sku_id)
            info = sku_info_map.get(sku_id_str)
            
            # Если товара нет в ответе batch, B2B трактует это как unavailable (удален)
            if not info:
                info = {
                    'product_id': str(item.product_id),
                    'name': 'Товар удален',
                    'price': 0,
                    'available_quantity': 0,
                    'is_available': False,
                    'unavailable_reason': 'PRODUCT_DELETED'
                }

            is_available = info['is_available']
            line_total = info['price'] * item.quantity if is_available else 0
            
            if is_available:
                subtotal += line_total
                items_count += item.quantity
            else:
                unavailable_count += 1

            cart_items_response.append({
                'sku_id': sku_id_str,
                'product_id': info['product_id'],
                'name': info['name'],
                'quantity': item.quantity,
                'unit_price': info['price'],
                'line_total': line_total,
                'available_quantity': info['available_quantity'],
                'is_available': is_available,
                'unavailable_reason': info['unavailable_reason']
            })

        return {
            'id': str(user.id) if user else session_id,
            'items': cart_items_response,
            'items_count': items_count,
            'subtotal': subtotal,
            'is_valid': unavailable_count == 0,
            'unavailable_count': unavailable_count
        }

    @classmethod
    def add_item(cls, request, sku_id: str, quantity: int):
        from .models import CartItem
        user, session_id = cls._get_identity(request)
        
        # 1. Проверка в B2B (получаем product_id и валидируем доступность)
        url = f'{cls.b2b_client.base_url}/api/v1/public/skus/{sku_id}'
        try:
            sku_data = cls.b2b_client._call_b2b(url,params={}, method='GET')
        except ValueError:
            raise ValueError("SKU not found or unavailable")
        except B2BUnavailableError:
            raise B2BUnavailableError("B2B service unavailable")
            
        product_id = sku_data.get('product_id')
        active_qty = sku_data.get('active_quantity', 0)
        
        if active_qty < quantity:
            raise ValueError("Insufficient stock")
            
        # 2. Сохранение в БД
        with transaction.atomic():
            if user:
                item, created = CartItem.objects.get_or_create(
                    user=user, sku_id=sku_id,
                    defaults={'product_id': product_id, 'quantity': quantity}
                )
            else:
                item, created = CartItem.objects.get_or_create(
                    session_id=session_id, sku_id=sku_id,
                    defaults={'product_id': product_id, 'quantity': quantity}
                )
                
            if not created:
                item.quantity += quantity
                item.save()
                
        return created

    @classmethod
    def update_item(cls, request, sku_id: str, quantity: int):
        from .models import CartItem
        user, session_id = cls._get_identity(request)
        
        url = f'{cls.b2b_client.base_url}/api/v1/public/skus/{sku_id}'
        try:
            sku_data = cls.b2b_client._call_b2b(url, params={}, method='GET')
        except ValueError:
            raise ValueError("SKU not found")
        except B2BUnavailableError:
            raise B2BUnavailableError("B2B service unavailable")
            
        if sku_data.get('active_quantity', 0) < quantity:
            raise ValueError("Insufficient stock for new quantity")

        if user:
            item = CartItem.objects.filter(user=user, sku_id=sku_id).first()
        else:
            item = CartItem.objects.filter(session_id=session_id, sku_id=sku_id).first()
            
        if not item:
            raise ValueError("Item not found in cart")
            
        item.quantity = quantity
        item.save()
        return item

    @classmethod
    def delete_item(cls, request, sku_id: str):
        from .models import CartItem
        user, session_id = cls._get_identity(request)
        
        if user:
            CartItem.objects.filter(user=user, sku_id=sku_id).delete()
        else:
            CartItem.objects.filter(session_id=session_id, sku_id=sku_id).delete()

    @classmethod
    def clear_cart(cls, request):
        from .models import CartItem
        user, session_id = cls._get_identity(request)
        
        if user:
            CartItem.objects.filter(user=user).delete()
        else:
            CartItem.objects.filter(session_id=session_id).delete()

    @classmethod
    def merge_cart(cls, session_id: str, user):
        from .models import CartItem
        """Слияние гостевой корзины с пользовательской (MAX quantity)"""
        guest_items = CartItem.objects.filter(session_id=session_id, user__isnull=True)
        
        with transaction.atomic():
            for g_item in guest_items:
                auth_item = CartItem.objects.filter(user=user, sku_id=g_item.sku_id).first()
                if auth_item:
                    # Конфликт: берем MAX, как указано в flowchart
                    auth_item.quantity = max(auth_item.quantity, g_item.quantity)
                    auth_item.save()
                    g_item.delete()
                else:
                    # Перенос
                    g_item.user = user
                    g_item.session_id = None
                    g_item.save()
                    
    @classmethod
    def validate_cart(cls, request):
        cart_data = cls.get_cart(request)
        issues = []
        
        for item in cart_data['items']:
            if not item['is_available']:
                issues.append({
                    'sku_id': item['sku_id'],
                    'type': item['unavailable_reason'] or 'PRODUCT_DELETED',
                    'message': f"Товар недоступен: {item['unavailable_reason']}"
                })
            elif item['quantity'] > item['available_quantity']:
                issues.append({
                    'sku_id': item['sku_id'],
                    'type': 'QUANTITY_REDUCED',
                    'message': f"Остаток уменьшился. Доступно: {item['available_quantity']}",
                    'old_value': item['quantity'],
                    'new_value': item['available_quantity']
                })
                
        return {
            'is_valid': len(issues) == 0,
            'cart': cart_data,
            'issues': issues
        }