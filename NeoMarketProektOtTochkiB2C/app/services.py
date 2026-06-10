import requests
import uuid
from django.conf import settings
from django.core.cache import cache
from .exceptions import B2BUnavailableError, BlockedProductError

class B2BClient:
    """Прокси-клиент для вызовов B2B-сервиса (синхронная версия)"""
    
    def __init__(self):
        self.base_url = settings.B2B_BASE_URL
        self.service_key = settings.B2B_SERVICE_KEY
        self.timeout = (5.0, 10.0)  # (connect timeout, read timeout) в секундах
    
    def _get_headers(self) -> dict:
        return {'X-Service-Key': self.service_key, 'Content-Type': 'application/json'}

    def _call_b2b_by_func(self,url,params,data,func):
        return func(
                    url, 
                    params=params, 
                    data=data,
                    headers=self._get_headers(),
                    timeout=self.timeout
                )

    def _call_b2b(self,url,params,data=None,method='GET'):
        if method=='GET' or method=='POST':
            if method=='GET':
                response = self._call_b2b_by_func(url,params,data,requests.get)
            if method=='POST':
                response = self._call_b2b_by_func(url,params,data,requests.post)
            response.raise_for_status()
            return response.json()
        raise ValueError(f'There are no urls with method {method}')
    
    def get_public_products(
        self,
        category_id: str = None,
        filters: dict = None,
        sort: str = None,
        limit: int = 20,
        offset: int = 0,
        search: str = None
    ) -> dict:
        """Вызов GET /api/v1/public/products из B2B (синхронный)"""
        params = {
            'limit': limit,
            'offset': offset,
        }
        
        if category_id:
            params['category_id'] = category_id
        if search:
            params['search'] = search
        if sort:
            params['sort'] = self._map_sort_param(sort)
        
        # Преобразуем filter[field]=value в flat params для B2B
        if filters:
            for key, value in filters.items():
                param_key = f'filters[{key}]'
                if isinstance(value, list):
                    params[param_key] = value
                else:
                    params[param_key] = [value]
        
        
        try:
            b2b_answer = self._call_b2b(f'{self.base_url}/api/v1/public/products',params)
            return self._transform_products_response(b2b_answer)
            
        except requests.exceptions.ConnectionError:
            raise B2BUnavailableError('B2B service unavailable - connection error')
        except requests.exceptions.Timeout:
            raise B2BUnavailableError('B2B service timeout')
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise ValueError('Category not found')
            raise B2BUnavailableError(f'B2B HTTP error: {e.response.status_code}')
        except requests.exceptions.RequestException as e:
            raise B2BUnavailableError(f'B2B service error: {e}')
    
    def get_facets(
        self,
        category_id: str,
        filters: dict = None
    ) -> dict:
        """Получение фасетов с кэшированием (синхронный)"""
        # Ключ кэша: категория + отсортированные фильтры
        cache_key = f'facets:{category_id}:{hash(frozenset((k, tuple(v) if isinstance(v,list) else v) for k,v in (filters or {}).items()))}'
        
        if cached := cache.get(cache_key):
            return cached
        
        params = {'category_id': category_id}
        if filters:
            for key, value in filters.items():
                param_key = f'filters[{key}]'
                if isinstance(value, list):
                    params[param_key] = value
                else:
                    params[param_key] = [value]
        
        url = f'{self.base_url}/api/v1/public/products/facets'
        
        try:            
            data = self._call_b2b(url,params)
            cache.set(cache_key, data, settings.FACETS_CACHE_TTL)
            return data
            
        except requests.exceptions.RequestException:
            # При недоступности B2B возвращаем пустые фасеты (не блокируем каталог)
            return {'facets': []}
    
    def _map_sort_param(self, sort: str) -> str:
        """Маппинг сортировки b2c -> b2b, так как эти параметры разные в спеках"""
        mapping = {
            'price_asc': 'price_asc',
            'price_desc': 'price_desc', 
            'popularity': 'popular',
            'new': 'created_desc',
        }
        return mapping.get(sort, 'popular')
    
    def _transform_products_response(self, b2b_data: dict) -> dict:
        """Трансформация ответа B2B в формат b2c.yaml: PaginatedCatalogProducts"""
        #has_stock
        data = {'product_ids': [item['id'] for item in b2b_data.get('items', [])]}
        url = f'{self.base_url}/api/v1/public/products/batch'
        params = {}
        if len(data['product_ids'])>0:
            products_data = self._call_b2b(url=url,params=params,data=data,method='POST')
            has_stock_dict = dict([[dat['id'],sum([sku['active_quantity'] for sku in dat['skus']])>0] for dat in products_data])
        else:
            has_stock_dict = {}
        #has_stock

        # has_stock_dict пустой, только если b2b_data.get('items', []) пустой. А тогда и _transform_product_card вызовется 0 раз.
        return {
            'items': [self._transform_product_card(item,has_stock_dict[item['id']]) for item in b2b_data.get('items', [])],
            'total_count': b2b_data.get('total_count', 0),
            'limit': b2b_data.get('limit', 20),
            'offset': b2b_data.get('offset', 0),
        }
    
    def _transform_product_card(self, b2b_item: dict, has_stock) -> dict:
        """Трансформация ProductPublicShortResponse -> CatalogProductCard"""
        cover_image = b2b_item.get('cover_image',None)
        images = []
        if not(cover_image is None):
            images = [{'id': uuid.uuid4(),'url': cover_image, 'ordering': 0}]

        return {
            'id': b2b_item['id'],
            'name': b2b_item['title'],
            'slug': b2b_item['slug'],
            'min_price': b2b_item['min_price'],
            'has_stock': has_stock,
            'images': images,
        }

    def get_product_detail(self, id: uuid.UUID):
        url = f'{self.base_url}/api/v1/public/products/{id}'
        params = {}

        try:
            b2b_answer = self._call_b2b(url=url,params=params,method='GET')
            if b2b_answer['status']=='BLOCKED' or b2b_answer['status']=='HARD_BLOCKED':
                raise BlockedProductError('Товар недоступен')
            return self._transform_product_from_uuid_get(b2b_answer)

        except requests.exceptions.ConnectionError:
            raise B2BUnavailableError('B2B service unavailable - connection error')
        except requests.exceptions.Timeout:
            raise B2BUnavailableError('B2B service timeout')
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise ValueError('Product not found')
            raise B2BUnavailableError(f'B2B HTTP error: {e.response.status_code}')
        except requests.exceptions.RequestException as e:
            raise B2BUnavailableError(f'B2B service error: {e}')

    def _transform_product_from_uuid_get(self,b2b_item):
        return {
            'id': b2b_item['id'],
            'name': b2b_item['title'],
            'slug': b2b_item['slug'],
            'min_price': min(sku['price'] for sku in b2b_item['skus']),
            'has_stock': sum(sku['active_quantity'] for sku in b2b_item['skus'])>0,
            'images': b2b_item['images'],
            'description': b2b_item['description'],
            'skus':[self._transform_sku(sku) for sku in b2b_item['skus']]
        }

    def _transform_sku(self,b2b_sku):
        return {
          "id": b2b_sku['id'],
          "name": b2b_sku['name'],
          "price": b2b_sku['price'],
          "available_quantity": b2b_sku['active_quantity'],
          "images": b2b_sku['images']
        }
    def get_products_batch(self, product_ids: list[str]) -> list[dict]:
        """Вызов GET/POST /api/v1/public/products/batch для валидации перед резервом"""
        url = f'{self.base_url}/api/v1/public/products/batch'
        data = {'product_ids': [pid for pid in product_ids]}
        try:
            return self._call_b2b(url=url, params={}, data=data, method='POST')
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise ValueError('Product not found')

    def reserve_inventory(self, idempotency_key: uuid.UUID, order_id: uuid.UUID, items: list[dict]) -> dict:
        """Вызов POST /api/v1/inventory/reserve (all-or-nothing)"""
        url = f'{self.base_url}/api/v1/inventory/reserve'
        data = {
            'idempotency_key': str(idempotency_key),
            'order_id': str(order_id),
            'items': [{'sku_id': str(i['sku_id']), 'quantity': i['quantity']} for i in items]
        }
        try:
            resp = self._call_b2b(url=url, params={}, data=data, method='POST')
            return resp
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 409:
                return e.response.json()
            if e.response.status_code == 404:
                raise e

    def unreserve_inventory(self, order_id: str, items: list[dict]) -> dict:
        """Вызов POST /api/v1/inventory/unreserve в B2B"""
        url = f'{self.base_url}/api/v1/inventory/unreserve'
        data = {
            'order_id': order_id,
            'items': items
        }
        try:
            return self._call_b2b(url=url, params={}, data=data, method='POST')
        except requests.exceptions.HTTPError as e:
            raise B2BUnavailableError(f'B2B unreserve failed: {e}')
        except requests.exceptions.Timeout as e:
            raise B2BUnavailableError(f'B2B unreserve failed: {e}')
        