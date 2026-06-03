import uuid
from django.db import models
from django.conf import settings

class CartItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='cart_items'
    )
    session_id = models.UUIDField(null=True, blank=True, db_index=True)
    sku_id = models.UUIDField(db_index=True)
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cart_items'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(user__isnull=False) | models.Q(session_id__isnull=False),
                name='cart_identity_check'
            ),
            models.UniqueConstraint(
                fields=['user', 'sku_id'],
                name='unique_user_sku',
                condition=models.Q(user__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['session_id', 'sku_id'],
                name='unique_session_sku',
                condition=models.Q(session_id__isnull=False)
            ),
        ]
        indexes = [
            models.Index(fields=['session_id']),
            models.Index(fields=['user', 'sku_id']),
        ]

    def __str__(self):
        return f"CartItem(id={self.id}, sku={self.sku_id}, qty={self.quantity})"