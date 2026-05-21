import httpx
from django.conf import settings
from django.core.cache import cache
from .exceptions import B2BUnavailableError

class B2BClient:
    """Прокси-клиент для вызовов B2B-сервиса"""
    
    def __init__(self):
        self.base_url = settings.B2B_BASE_URL
        self.service_key = settings.B2B_SERVICE_KEY
        self.timeout = httpx.Timeout(10.0, connect=5.0)
    
    def _get_headers(self) -> dict:
        return {'X-Service-Key': self.service_key}
    
    async def get_public_products(
        self,
        category_id: str = None,
        filters: dict = None,
        sort: str = None,
        limit: int = 20,
        offset: int = 0,
        search: str = None
    ) -> dict:
        """Вызов GET /api/v1/public/products из B2B"""
        params = {
            'limit': limit,
            'offset': offset,
            'category_id': category_id,
            'search': search,
            'sort': self._map_sort_param(sort),
        }
        # Преобразуем filter[field]=value в flat params для B2B
        if filters:
            for key, value in filters.items():
                if isinstance(value, list):
                    params[f'filters[{key}]'] = value
                else:
                    params[f'filters[{key}]'] = [value]
        
        url = f'{self.base_url}/api/v1/public/products'
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params, headers=self._get_headers())
                response.raise_for_status()
                return self._transform_products_response(response.json())
        except httpx.ConnectError:
            raise B2BUnavailableError('B2B service unavailable')
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ValueError('Category not found')  # Для обработки 404 на уровне view
            raise
    
    async def get_facets(
        self,
        category_id: str,
        filters: dict = None
    ) -> dict:
        """Получение фасетов с кэшированием"""
        # Ключ кэша: категория + отсортированные фильтры
        cache_key = f'facets:{category_id}:{hash(frozenset((k, tuple(v) if isinstance(v,list) else v) for k,v in (filters or {}).items()))}'
        
        if cached := cache.get(cache_key):
            return cached
        
        params = {'category_id': category_id}
        if filters:
            for key, value in filters.items():
                params[f'filters[{key}]'] = value if isinstance(value, list) else [value]
        
        url = f'{self.base_url}/api/v1/public/products/facets'  # ⚠️ Нужно добавить в b2b.yaml!
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params, headers=self._get_headers())
                response.raise_for_status()
                data = response.json()
                cache.set(cache_key, data, settings.FACETS_CACHE_TTL)
                return data
        except httpx.ConnectError:
            # При недоступности B2B возвращаем пустые фасеты (не блокируем каталог)
            return {'facets': []}
    
    def _map_sort_param(self, sort: str) -> str:
        """Маппинг сортировки b2c -> b2b"""
        mapping = {
            'price_asc': 'price_asc',
            'price_desc': 'price_desc', 
            'popularity': 'popular',
            'new': 'created_desc',  # b2c: new -> b2b: created_desc
        }
        return mapping.get(sort, 'popular')  # default
    
    def _transform_products_response(self, b2b_data: dict) -> dict:
        """Трансформация ответа B2B в формат b2c.yaml: PaginatedCatalogProducts"""
        return {
            'items': [self._transform_product_card(item) for item in b2b_data.get('items', [])],
            'total_count': b2b_data.get('total_count', 0),
            'limit': b2b_data.get('limit', 20),
            'offset': b2b_data.get('offset', 0),
        }
    
    def _transform_product_card(self, b2b_item: dict) -> dict:
        """Трансформация ProductPublicShortResponse -> CatalogProductCard"""
        # Берём минимальную цену из SKU, определяем наличие
        skus = b2b_item.get('skus', [])
        min_price = min((sku['price'] - sku.get('discount', 0) for sku in skus), default=None)
        has_stock = any(sku.get('active_quantity', 0) > 0 for sku in skus)
        
        return {
            'id': b2b_item['id'],
            'name': b2b_item['title'],  # b2b: title -> b2c: name
            'slug': b2b_item.get('slug'),
            'category': {'id': b2b_item['category_id'], 'name': '', 'level': 0, 'path': []},  # ⚠️ Нужно джойнить с категориями
            'min_price': min_price,
            'old_price': None,  # Можно вычислять из discount
            'has_stock': has_stock,
            'rating': None,  # ⚠️ Добавить в b2b, если нужно
            'reviews_count': 0,
            'images': b2b_item.get('images', []),
            'seller': {'id': b2b_item['seller_id'], 'display_name': ''},  # ⚠️ Нужен эндпоинт для имени продавца
        }
