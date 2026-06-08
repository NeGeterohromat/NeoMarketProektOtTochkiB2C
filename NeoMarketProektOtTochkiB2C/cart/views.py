from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from app.exceptions import error_response
from .services import CartService
from .serializers import CartItemAddSerializer, CartItemUpdateSerializer

class CartAPIView(APIView):
    def get(self, request):
        try:
            cart = CartService.get_cart(request)
            return Response(cart, status=status.HTTP_200_OK)
        except ValueError as e:
            return error_response('INVALID_REQUEST',str(e),status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request):
        CartService.clear_cart(request)
        return Response(status=status.HTTP_204_NO_CONTENT)

class CartItemAPIView(APIView):
    def post(self, request):
        serializer = CartItemAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            is_created = CartService.add_item(
                request, 
                serializer.validated_data['sku_id'], 
                serializer.validated_data['quantity']
            )
            cart = CartService.get_cart(request)
            status_code = status.HTTP_201_CREATED if is_created else status.HTTP_200_OK
            return Response(cart, status=status_code)
        except ValueError as e:
            if "Insufficient stock" in str(e) or "exceeds" in str(e):
                return error_response('INVALID_REQUEST',str(e),status=status.HTTP_409_CONFLICT)
            return error_response('INVALID_REQUEST',str(e),status=status.HTTP_404_NOT_FOUND)

    def patch(self, request, sku_id: str):
        serializer = CartItemUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            CartService.update_item(request, sku_id, serializer.validated_data['quantity'])
            cart = CartService.get_cart(request)
            return Response(cart, status=status.HTTP_200_OK)
        except ValueError as e:
            if "Insufficient stock" in str(e):
                return error_response('INVALID_REQUEST',str(e),status=status.HTTP_409_CONFLICT)
            return error_response('INVALID_REQUEST',str(e),status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, sku_id: str):
        CartService.delete_item(request, sku_id)
        cart = CartService.get_cart(request)
        return Response(cart, status=status.HTTP_200_OK)

class CartValidateAPIView(APIView):
    def post(self, request):
        validation = CartService.validate_cart(request)
        return Response(validation, status=status.HTTP_200_OK)

class CartMergeAPIView(APIView):
    def post(self, request):
        if not request.user.is_authenticated:
            return error_response('UNAUTHORIZED','Unauthorized user',status=status.HTTP_401_UNAUTHORIZED)
            
        session_id = request.headers.get('X-Session-Id')
        if not session_id:
            return error_response('INVALID_REQUEST','X-Session-Id header required for merge',status=status.HTTP_400_BAD_REQUEST)
            
        CartService.merge_cart(session_id, request.user)
        cart = CartService.get_cart(request)
        return Response(cart, status=status.HTTP_200_OK)