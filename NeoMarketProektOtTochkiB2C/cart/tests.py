import uuid
from unittest.mock import patch
from django.test import override_settings
from django.urls import reverse
from app.services import B2BClient
from rest_framework.test import APITestCase, APIClient
from django.contrib.auth import get_user_model
from .models import CartItem
from app.services import B2BClient

User = get_user_model()

@override_settings(B2B_BASE_URL='http://mock-b2b.local')
class CartAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='password')
        self.sku_id = uuid.uuid4()
        self.product_id = uuid.uuid4()
        self.session_id = str(uuid.uuid4())

    def _mock_b2b_get_sku(self, available=True, qty=10):
        return {
            'id': str(self.sku_id),
            'product_id': str(self.product_id),
            'name': 'Test SKU',
            'price': 1000,
            'active_quantity': qty if available else 0,
        }

    def _mock_b2b_batch_products(self, available=True, qty=10):
        # Возвращает ПЛОСКИЙ СПИСОК, как требует b2b.yaml
        return [{
            'id': str(self.product_id),
            'title': 'Test Product',
            'status': 'MODERATED' if available else 'BLOCKED',
            'skus': [{
                'id': str(self.sku_id),
                'name': 'Test SKU',
                'price': 1000,
                'active_quantity': qty if available else 0
            }]
        }]

    @patch('cart.services.requests.post')
    @patch('cart.services.requests.get')
    def test_add_sku_increments_quantity_if_already_in_cart(self, mock_get, mock_post):
        mock_get.return_value.json.return_value = self._mock_b2b_get_sku()
        mock_get.return_value.raise_for_status = lambda: None
        
        self.client.credentials(HTTP_X_SESSION_ID=self.session_id)
        
        # Первое добавление
        resp1 = self.client.post('/api/v1/cart/items', {'sku_id': str(self.sku_id), 'quantity': 2})
        self.assertEqual(resp1.status_code, 201)
        
        # Повторное добавление
        resp2 = self.client.post('/api/v1/cart/items', {'sku_id': str(self.sku_id), 'quantity': 3})
        self.assertEqual(resp2.status_code, 200)
        
        cart = resp2.json()
        item = next(i for i in cart['items'] if i['sku_id'] == str(self.sku_id))
        self.assertEqual(item['quantity'], 5) # 2 + 3

    @patch('cart.services.requests.post')
    @patch('cart.services.requests.get')
    def test_get_cart_enriched_with_b2b_data(self, mock_get, mock_post):
        mock_get.return_value.json.return_value = self._mock_b2b_get_sku()
        mock_get.return_value.raise_for_status = lambda: None
        
        self.client.credentials(HTTP_X_SESSION_ID=self.session_id)
        self.client.post('/api/v1/cart/items', {'sku_id': str(self.sku_id), 'quantity': 2})
        
        # Мокаем batch-ответ для GET /cart
        mock_post.return_value.json.return_value = self._mock_b2b_batch_products()
        mock_post.return_value.raise_for_status = lambda: None
        
        resp = self.client.get('/api/v1/cart')
        self.assertEqual(resp.status_code, 200)
        
        data = resp.json()
        self.assertEqual(data['items_count'], 2)
        self.assertEqual(data['subtotal'], 2000) # 2 * 1000
        self.assertTrue(data['is_valid'])
        
        item = data['items'][0]
        self.assertEqual(item['unit_price'], 1000)
        self.assertTrue(item['is_available'])

    @patch('cart.services.requests.post')
    @patch('cart.services.requests.get')
    def test_unavailable_sku_shown_with_reason(self, mock_get, mock_post):
        # 1. Добавляем товар (он доступен)
        mock_get.return_value.json.return_value = self._mock_b2b_get_sku(available=True, qty=5)
        mock_get.return_value.raise_for_status = lambda: None
        
        self.client.credentials(HTTP_X_SESSION_ID=self.session_id)
        self.client.post('/api/v1/cart/items', {'sku_id': str(self.sku_id), 'quantity': 2})
        
        # 2. При GET /cart товар стал заблокирован (мокаем POST batch)
        mock_post.return_value.json.return_value = self._mock_b2b_batch_products(available=False, qty=0)
        mock_post.return_value.raise_for_status = lambda: None
        
        resp = self.client.get('/api/v1/cart')
        self.assertEqual(resp.status_code, 200)
        
        data = resp.json()
        item = next(i for i in data['items'] if i['sku_id'] == str(self.sku_id))
        
        self.assertFalse(item['is_available'])
        self.assertEqual(item['unavailable_reason'], 'PRODUCT_BLOCKED')
        self.assertEqual(item['line_total'], 0) # Не входит в total_amount
        self.assertEqual(data['subtotal'], 0)
        self.assertFalse(data['is_valid'])

    @patch('cart.services.requests.post')
    @patch('cart.services.requests.get')
    def test_guest_cart_merged_on_login(self, mock_get, mock_post):
        mock_get.return_value.json.return_value = self._mock_b2b_get_sku()
        mock_get.return_value.raise_for_status = lambda: None
        
        # 1. Гость добавляет 3 шт.
        self.client.credentials(HTTP_X_SESSION_ID=self.session_id)
        self.client.post('/api/v1/cart/items', {'sku_id': str(self.sku_id), 'quantity': 3})
        
        # 2. Пользователь уже имеет 5 шт. этого SKU
        CartItem.objects.create(user=self.user, sku_id=self.sku_id, product_id=self.product_id, quantity=5)
        
        # 3. Авторизуемся и мержим
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_SESSION_ID=self.session_id) 
        
        resp = self.client.post('/api/v1/cart/merge')
        self.assertEqual(resp.status_code, 200)
        
        # Проверка: quantity = MAX(3, 5) = 5
        cart = resp.json()
        item = next(i for i in cart['items'] if i['sku_id'] == str(self.sku_id))
        self.assertEqual(item['quantity'], 5)
        
        # Проверка БД: гостевая запись удалена, осталась только пользовательская
        self.assertEqual(CartItem.objects.filter(session_id=self.session_id).count(), 0)
        self.assertEqual(CartItem.objects.filter(user=self.user).count(), 1)
        self.assertEqual(CartItem.objects.get(user=self.user).quantity, 5)