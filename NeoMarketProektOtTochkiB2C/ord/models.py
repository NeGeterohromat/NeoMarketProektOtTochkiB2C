import uuid
from django.db import models
from django.conf import settings

class OrderStatus(models.TextChoices):
    PAID = 'PAID', 'Оплачен'
    CREATED = 'CREATED', 'Создан'
    ASSEMBLING = 'ASSEMBLING', 'Собирается'
    DELIVERING = 'DELIVERING', 'Доставляется'
    DELIVERED = 'DELIVERED', 'Доставлен'
    CANCELLED = 'CANCELLED', 'Отменён'
    CANCEL_PENDING = 'CANCEL_PENDING', 'Ожидает отмены'

class Order(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='orders')
    idempotency_key = models.UUIDField(unique=True, db_index=True)
    address_id = models.UUIDField()
    payment_method_id = models.UUIDField()
    comment = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PAID)
    total_price = models.IntegerField(default=0)  # в копейках
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order {self.id} ({self.status})"

class OrderItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    sku_id = models.UUIDField()
    product_name = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField()
    unit_price = models.IntegerField()  # в копейках (фиксируется на момент чекаута)
    line_total = models.IntegerField()  # unit_price * quantity

    def __str__(self):
        return f"SKU {self.sku_id} x {self.quantity}"