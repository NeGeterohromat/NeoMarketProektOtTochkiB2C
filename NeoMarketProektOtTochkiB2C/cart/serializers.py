from rest_framework import serializers
import uuid

class CartItemAddSerializer(serializers.Serializer):
    sku_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)

class CartItemUpdateSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)

class CartMergeRequestSerializer(serializers.Serializer):
    # Тело пустое, session_id берется из заголовка
    pass