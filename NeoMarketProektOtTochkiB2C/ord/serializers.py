
from rest_framework import serializers
from .models import Order, OrderItem, OrderStatus
from django.utils import timezone

class OrderItemSnapshotSerializer(serializers.Serializer):
    sku_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    unit_price = serializers.IntegerField(min_value=0)

class OrderCreateSerializer(serializers.Serializer):
    address_id = serializers.UUIDField()
    payment_method_id = serializers.UUIDField()
    comment = serializers.CharField(required=False, allow_blank=True, default='')
    items_snapshot = OrderItemSnapshotSerializer(many=True)

class OrderItemBaseResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['id', 'sku_id', 'product_id', 'quantity', 'unit_price', 'line_total']

class OrderBaseResponseSerializer(serializers.ModelSerializer):
    items = OrderItemBaseResponseSerializer(many=True, read_only=True)
    class Meta:
        model = Order
        fields = ['id', 'user', 'address_id', 'payment_method_id', 'comment', 'status', 'total_price', 'items', 'created_at']

from rest_framework import serializers
from .models import Order, OrderItem, OrderStatus
from django.utils import timezone

class OrderCancelRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)

class OrderItemResponseSerializer(serializers.ModelSerializer):
    name = serializers.CharField(read_only=True) # Заполняется в сервисе или через доп. запрос
    image_url = serializers.CharField(read_only=True, allow_null=True)

    class Meta:
        model = OrderItem
        fields = ['sku_id', 'product_id', 'name', 'sku_code', 'quantity', 'unit_price', 'line_total', 'image_url']

class OrderStatusHistorySerializer(serializers.Serializer):
    status = serializers.CharField()
    changed_at = serializers.DateTimeField()
    reason = serializers.CharField(allow_null=True)

class OrderResponseSerializer(serializers.ModelSerializer):
    buyer_id = serializers.UUIDField(source='user.id')
    number = serializers.CharField(source='id', read_only=True) # Заглушка для human-readable number, если нет отдельного поля
    status_history = serializers.SerializerMethodField()
    items = OrderItemResponseSerializer(many=True, read_only=True)
    subtotal = serializers.IntegerField(source='total_price')
    delivery_cost = serializers.IntegerField(default=0)
    total = serializers.IntegerField(source='total_price')
    address = serializers.SerializerMethodField()
    payment_method = serializers.SerializerMethodField()
    cancel_reason = serializers.CharField(source='comment', read_only=True) # Используем comment как reason для простоты
    
    class Meta:
        model = Order
        fields = [
            'id', 'number', 'buyer_id', 'status', 'status_history', 'items',
            'subtotal', 'delivery_cost', 'total', 'address', 'payment_method',
            'comment', 'cancel_reason', 'created_at', 'paid_at', 'delivered_at'
        ]

    def get_status_history(self, obj):
        # Формируем историю на основе текущего состояния. В реальном проекте это отдельная модель OrderStatusHistory
        return [
            {
                'status': obj.status,
                'changed_at': timezone.now(),
                'reason': obj.comment if obj.status == OrderStatus.CANCELLED else None
            }
        ]

    def get_address(self, obj):
        # Заглушка, так как address_id - это UUID. В реальном проекте здесь был бы запрос к сервису адресов или денормализованные данные
        return {
            'id': str(obj.address_id),
            'country': '', 'region': '', 'city': '', 'street': '', 'building': '',
            'apartment': '', 'postal_code': '', 'recipient_name': '', 'recipient_phone': '',
            'is_default': False, 'comment': '', 'created_at': obj.created_at.isoformat()
        }

    def get_payment_method(self, obj):
        # Заглушка для payment_method_id
        return {
            'id': str(obj.payment_method_id),
            'type': 'CARD', 'card_last4': '0000', 'card_brand': 'VISA', 'is_default': False,
            'created_at': obj.created_at.isoformat()
        }