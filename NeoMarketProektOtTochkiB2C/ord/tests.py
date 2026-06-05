import uuid
from django.test import override_settings
from app.services import B2BClient
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from unittest.mock import patch, MagicMock
from .models import Order
from app.services import B2BClient
import requests

User = get_user_model()

class OrderCheckoutTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_authenticate(user=self.user)
        self.idempotency_key = str(uuid.uuid4())
        self.headers = {'HTTP_IDEMPOTENCY_KEY': self.idempotency_key}
        self.valid_payload = {
            'address_id': str(uuid.uuid4()),
            'payment_method_id': str(uuid.uuid4()),
            'comment': 'Test order',
            'items_snapshot': [
                {'sku_id': str(uuid.uuid4()), 'quantity': 2, 'unit_price': 150000}
            ]
        }

    def test_checkout_creates_paid_order_with_fixed_prices(self):
        """Happy path: успешный чекаут, статус PAID, цены зафиксированы"""
        with patch('app.services.B2BClient.reserve_inventory') as mock_reserve:
            mock_reserve.return_value = {'status': 'RESERVED', 'order_id': str(uuid.uuid4())}
            
            response = self.client.post('/api/v1/orders/', self.valid_payload, format='json', **self.headers)
            
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertEqual(response.data['status'], 'PAID')
            self.assertEqual(response.data['total_price'], 300000) # 150000 * 2
            self.assertEqual(len(response.data['items']), 1)
            self.assertEqual(response.data['items'][0]['unit_price'], 150000)
            self.assertEqual(response.data['items'][0]['line_total'], 300000)
            self.assertTrue(Order.objects.filter(idempotency_key=self.idempotency_key).exists())

    def test_partial_reserve_failure_returns_409(self):
        """Unhappy path: B2B возвращает 409 с failed_items"""
        failed_items = [{'sku_id': '11111111-1111-1111-1111-111111111111', 'reason': 'OUT_OF_STOCK'}]
        with patch('app.services.B2BClient.reserve_inventory') as mock_reserve:
            mock_reserve.return_value = {'status': 'FAILED', 'failed_items': failed_items}
            
            response = self.client.post('/api/v1/orders/', self.valid_payload, format='json', **self.headers)
            
            self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
            self.assertEqual(response.data['code'], 'RESERVE_FAILED')
            self.assertEqual(response.data['failed_items'], failed_items)
            self.assertFalse(Order.objects.filter(idempotency_key=self.idempotency_key).exists())

    def test_idempotency_returns_existing_order(self):
        """Unhappy path: повторный запрос с тем же idempotency_key возвращает существующий заказ"""
        # Создаём заказ вручную
        existing_order = Order.objects.create(
            user=self.user, idempotency_key=self.idempotency_key,
            address_id=uuid.uuid4(), payment_method_id=uuid.uuid4(),
            status='PAID', total_price=100000
        )
        
        response = self.client.post('/api/v1/orders/', self.valid_payload, format='json', **self.headers)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['id'], str(existing_order.id))
        # Убедимся, что новый заказ не создался
        self.assertEqual(Order.objects.filter(idempotency_key=self.idempotency_key).count(), 1)

    def test_b2b_unavailable_returns_503(self):
        """Unhappy path: B2B недоступен -> 503"""
        with patch.object(B2BClient, '_call_b2b_by_func') as mock_b2b:
            # B2BClient должен выбрасывать ValueError для 404
            real_response = requests.Response()
            real_response.status_code = 404
            real_response.reason = "Internal Server Error"
            real_response.url = "https://api.example.com/data"
            real_response._content = b'{"detail": "server crashed"}'
            real_response.encoding = 'utf-8'

            mock_b2b.return_value = real_response

            response = self.client.post('/api/v1/orders/', self.valid_payload, format='json', **self.headers)
                
            self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
            self.assertEqual(response.data['code'], 'B2B_UNAVAILABLE')