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
        """Возвращает (user, session_id). Если пользователь авторизован, session_id игнорируется."""
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
            items = CartItem.objects.filter(user=user)
        else:
            items = CartItem.objects.filter(session_id=session_id)
            
        sku_ids = list(items.values_list('sku_id', flat=True))
        b2b_info = cls.b2b_client.get_skus_info(sku_ids)
        
        cart_items_response = []
        subtotal = 0
        items_count = 0
        unavailable_count = 0

        for item in items:
            info = b2b_info.get(str(item.sku_id), {})
            is_available = info.get('is_available', False)
            unavailable_reason = info.get('unavailable_reason')
            
            # Если товара нет в B2B вообще, считаем его удаленным
            if not info:
                is_available = False
                unavailable_reason = 'PRODUCT_DELETED'
                info = {'price': 0, 'available_quantity': 0, 'product_id': str(uuid.uuid4()), 'name': 'Unknown'}

            line_total = info['price'] * item.quantity if is_available else 0
            
            if is_available:
                subtotal += line_total
                items_count += item.quantity
            else:
                unavailable_count += 1

            cart_items_response.append({
                'sku_id': str(item.sku_id),
                'product_id': str(info['product_id']),
                'name': info['name'],
                'quantity': item.quantity,
                'unit_price': info['price'],
                'line_total': line_total,
                'available_quantity': info['available_quantity'],
                'is_available': is_available,
                'unavailable_reason': unavailable_reason
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
        
        # 1. Проверка в B2B перед добавлением
        b2b_info = cls.b2b_client.get_skus_info([sku_id])
        sku_info = b2b_info.get(str(sku_id))
        
        if not sku_info or not sku_info['is_available']:
            reason = sku_info['unavailable_reason'] if sku_info else 'PRODUCT_DELETED'
            raise ValueError(f"SKU unavailable: {reason}")
            
        if sku_info['available_quantity'] < quantity:
            raise ValueError("Insufficient stock")

        # 2. Сохранение в БД
        with transaction.atomic():
            if user:
                item, created = CartItem.objects.get_or_create(
                    user=user, sku_id=sku_id,
                    defaults={'quantity': quantity}
                )
            else:
                item, created = CartItem.objects.get_or_create(
                    session_id=session_id, sku_id=sku_id,
                    defaults={'quantity': quantity}
            )
            
            if not created:
                item.quantity += quantity
                # Проверка на превышение остатка после сложения
                if item.quantity > sku_info['available_quantity']:
                    raise ValueError("Total quantity exceeds available stock")
                item.save()
                
        return created # True = 201, False = 200

    @classmethod
    def update_item(cls, request, sku_id: str, quantity: int):
        from .models import CartItem
        user, session_id = cls._get_identity(request)
        
        b2b_info = cls.b2b_client.get_skus_info([sku_id])
        sku_info = b2b_info.get(str(sku_id))
        
        if sku_info and sku_info['available_quantity'] < quantity:
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
                    # Конфликт: берем MAX
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
