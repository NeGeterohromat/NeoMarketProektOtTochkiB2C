import uuid
import json
from django.test import override_settings
from app.services import B2BClient
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from unittest.mock import patch, MagicMock
from .models import Order, OrderItem, OrderStatus
from cart.models import CartItem
from app.exceptions import B2BUnavailableError
import requests

User = get_user_model()

class OrderCheckoutTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_authenticate(user=self.user)
        self.idempotency_key = str(uuid.uuid4())
        self.headers = {'HTTP_IDEMPOTENCY_KEY': self.idempotency_key}
        self.product_id = str(uuid.uuid4())
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
        with patch('app.services.B2BClient._call_b2b') as mock_reserve:
            def get_response_with_id(**kwargs):
                if 'batch' in kwargs['url']:
                    return [{'id': self.product_id,'skus':[{'id':self.valid_payload['items_snapshot'][0]['sku_id'],'name':'nnn'}]}]
                return {'status': 'RESERVED', 'order_id': str(kwargs['data']['order_id'])}

            mock_reserve.side_effect = get_response_with_id
            
            cart_item = CartItem.objects.create(user=self.user,
                                                product_id=self.product_id,
                                                sku_id=self.valid_payload['items_snapshot'][0]['sku_id'],
                                                quantity=self.valid_payload['items_snapshot'][0]['quantity'],
                                                )

            response = self.client.post('/api/v1/orders/', self.valid_payload, format='json', **self.headers)
            
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertIn('id',response.data)
            self.assertIn('buyer_id',response.data)
            self.assertEqual(response.data['status'], 'PAID')
            self.assertEqual(response.data['subtotal'], 300000) # 150000 * 2
            self.assertEqual(response.data['total'], 300000)
            self.assertEqual(response.data['address']['id'],self.valid_payload['address_id'])
            self.assertEqual(len(response.data['items']), 1)
            self.assertEqual(response.data['items'][0]['unit_price'], 150000)
            self.assertEqual(response.data['items'][0]['line_total'], 300000)
            self.assertTrue(Order.objects.filter(idempotency_key=self.idempotency_key).exists())

    def test_partial_reserve_failure_returns_409(self):
        """Unhappy path: B2B возвращает 409 с failed_items"""
        failed_items = [{'sku_id': '11111111-1111-1111-1111-111111111111', 'reason': 'OUT_OF_STOCK'}]
        with patch('app.services.B2BClient._call_b2b_by_func') as mock_reserve:
            real_response = requests.Response()
            real_response.status_code = 409
            real_response.reason = "VALIDATION_ERROR"
            real_response.url = "https://api.example.com/data"
            real_response._content = b'{"code": "VALIDATION_ERROR", "message": "Field title", "details": [{"sku_id": "11111111-1111-1111-1111-111111111111", "reason": "OUT_OF_STOCK"}]}'
            real_response.encoding = 'utf-8'

            # 2. Возвращаем его из мока. Методы .raise_for_status(), .json() и т.д. остаются реальными!
            mock_reserve.return_value = real_response
            
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
        item = OrderItem.objects.create(
                order=existing_order,
                sku_id=self.valid_payload['items_snapshot'][0]['sku_id'],
                product_id=self.product_id, # Опционально из кэша/B2B
                quantity=self.valid_payload['items_snapshot'][0]['quantity'],
                unit_price=self.valid_payload['items_snapshot'][0]['unit_price'],
                line_total=300000
            )
        with patch('app.services.B2BClient._call_b2b') as mock_batch:
            mock_batch.return_value = [{'id': self.product_id,'skus':[{'id':self.valid_payload['items_snapshot'][0]['sku_id'],'name':'nnn'}]}]

            response = self.client.post('/api/v1/orders/', self.valid_payload, format='json', **self.headers)
        
            self.assertEqual(response.status_code, status.HTTP_200_OK)
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

class OrderCancelTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.other_user = User.objects.create_user(username='otheruser', password='testpass')
        
        self.order = Order.objects.create(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            address_id=uuid.uuid4(),
            payment_method_id=uuid.uuid4(),
            status=OrderStatus.PAID,
            total_price=5000
        )
        self.order_item = OrderItem.objects.create(
            order=self.order,
            sku_id=uuid.uuid4(),
            product_id=uuid.uuid4(),
            quantity=2,
            unit_price=2500,
            line_total=5000
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch('ord.services.B2BClient._call_b2b')
    def test_cancel_paid_order_transitions_to_cancelled(self, mock_unreserve):
        """Happy path: успешная отмена оплаченного заказа"""
        mock_unreserve.side_effect = [{'status': 'UNRESERVED', 'processed_at': '2026-06-09T13:35:39.158Z'},
                                      [{'id': str(self.order_item.product_id),'skus':[{'id':str(self.order_item.sku_id),'name':'nnn'}]}]]
        
        response = self.client.post(f'/api/v1/orders/{self.order.id}/cancel/')
        
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.CANCELLED)
        self.assertEqual(response.json()['status'], 'CANCELLED')

    @patch('ord.services.B2BClient._call_b2b_by_func')
    def test_unreserve_failure_transitions_to_cancel_pending(self, mock_unreserve):
        """Unhappy path: B2B недоступен, заказ переходит в CANCEL_PENDING"""
        def get_real_response(status,text):
            real_response = requests.Response()
            real_response.status_code = status
            real_response.reason = "SERVER_ERROR"
            real_response.url = "https://api.example.com/data"
            real_response._content = text.encode('utf-8')
            real_response.encoding = 'utf-8'
            return real_response

        mock_unreserve.side_effect = [get_real_response(502,'{"code": "SERVER_ERROR", "message": "SERVER_ERROR"}'),
                                      get_real_response(200,json.dumps([{"id": str(self.order_item.product_id),"skus":[{"id":str(self.order_item.sku_id),"name":"nnn"}]}]))]

        
        response = self.client.post(f'/api/v1/orders/{self.order.id}/cancel/')
        
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.CANCEL_PENDING)
        self.assertEqual(response.json()['status'], 'CANCEL_PENDING')

    def test_cancel_assembling_order_returns_409(self):
        """Попытка отменить заказ в статусе ASSEMBLING возвращает 409"""
        self.order.status = OrderStatus.ASSEMBLING
        self.order.save()
        
        response = self.client.post(f'/api/v1/orders/{self.order.id}/cancel/')
        
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['code'], 'CANCEL_NOT_ALLOWED')
        self.assertEqual(response.json()['details']['current_status'], 'ASSEMBLING')

    def test_other_user_order_returns_404(self):
        """IDOR: попытка отменить чужой заказ возвращает 404 (не 403)"""
        self.client.force_authenticate(user=self.other_user)
        
        response = self.client.post(f'/api/v1/orders/{self.order.id}/cancel/')
        
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['code'], 'ORDER_NOT_FOUND')