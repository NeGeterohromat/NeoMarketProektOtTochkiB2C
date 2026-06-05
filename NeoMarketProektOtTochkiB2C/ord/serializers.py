
from rest_framework import serializers
from .models import Order, OrderItem

class OrderItemSnapshotSerializer(serializers.Serializer):
    sku_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    unit_price = serializers.IntegerField(min_value=0)

class OrderCreateSerializer(serializers.Serializer):
    address_id = serializers.UUIDField()
    payment_method_id = serializers.UUIDField()
    comment = serializers.CharField(required=False, allow_blank=True, default='')
    items_snapshot = OrderItemSnapshotSerializer(many=True)

class OrderItemResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['id', 'sku_id', 'product_name', 'quantity', 'unit_price', 'line_total']

class OrderResponseSerializer(serializers.ModelSerializer):
    items = OrderItemResponseSerializer(many=True, read_only=True)
    class Meta:
        model = Order
        fields = ['id', 'user', 'address_id', 'payment_method_id', 'comment', 'status', 'total_price', 'items', 'created_at']