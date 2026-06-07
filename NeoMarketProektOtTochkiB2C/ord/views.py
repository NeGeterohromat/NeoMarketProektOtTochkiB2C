import uuid
import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .serializers import OrderCreateSerializer, OrderResponseSerializer
from .services import OrderService, B2BClient
from app.exceptions import B2BUnavailableError, ReserveFailedError, CheckoutValidationError, error_response

class OrderCreateView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request, *args, **kwargs):
        # Извлечение Idempotency-Key
        idempotency_key_str = request.headers.get('Idempotency-Key')
        if not idempotency_key_str:
            return Response({'code': 'MISSING_IDEMPOTENCY', 'message': 'Header Idempotency-Key is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            idempotency_key = uuid.UUID(idempotency_key_str)
        except ValueError:
            return Response({'code': 'INVALID_IDEMPOTENCY', 'message': 'Invalid UUID format'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            b2b_client = B2BClient()
            order_service = OrderService(b2b_client)
            order = order_service.create_order(
                user=request.user,
                idempotency_key=idempotency_key,
                payload=serializer.validated_data
            )
            order_ser = OrderResponseSerializer(order)
            data= order_ser.data
            data['user'] = request.user
            print(order)
            print(data)
            return Response(order_service.transform_order_to_response(data), status=status.HTTP_201_CREATED)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return Response({'code': 'B2B_UNAVAILABLE', 'message': 'Сервис товаров временно недоступен, попробуйте позже'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            return Response({'code': 'B2B_UNAVAILABLE', 'message': 'Сервис товаров временно недоступен, попробуйте позже'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except CheckoutValidationError as e:
            return error_response('INVALID_QUANTITY','Количество должно быть не менее 1 для каждой позиции',status.HTTP_422_UNPROCESSABLE_ENTITY) 
        except ReserveFailedError as e:
            return Response({'code': 'RESERVE_FAILED', 'message': 'Не удалось зарезервировать товары', 'failed_items': getattr(e, 'failed_items', [])}, status=status.HTTP_409_CONFLICT)
        except B2BUnavailableError as e:
            return error_response('B2B_UNAVAILABLE','Сервис товаров временно недоступен, попробуйте позже',status.HTTP_503_SERVICE_UNAVAILABLE)