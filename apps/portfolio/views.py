from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from apps.portfolio.services.portfolio_generator import generate_fractional_portfolio
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

class PortfolioGenerateView(APIView):
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Generate a personalized Bayesvest fractional portfolio based on the user's latest Risk Assessment. Returns asset allocations with detailed reasoning for each decision.",
        responses={
            201: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'user_id': openapi.Schema(type=openapi.TYPE_STRING),
                    'risk_summary': openapi.Schema(type=openapi.TYPE_STRING, description="A human-readable explanation of the user's risk profile and what it means."),
                    'asset_allocation': openapi.Schema(type=openapi.TYPE_OBJECT, description="Dictionary mapping asset tickers to fractional weights (e.g. {'BTC': 0.6, 'AAPL': 0.4})"),
                    'expected_return_1y': openapi.Schema(type=openapi.TYPE_NUMBER),
                    'reasoning': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        description="Per-asset reasoning explaining why each asset was included and at what weight.",
                        items=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'ticker': openapi.Schema(type=openapi.TYPE_STRING),
                                'asset_name': openapi.Schema(type=openapi.TYPE_STRING),
                                'allocation_pct': openapi.Schema(type=openapi.TYPE_NUMBER),
                                'expected_return': openapi.Schema(type=openapi.TYPE_NUMBER),
                                'volatility': openapi.Schema(type=openapi.TYPE_NUMBER),
                                'suitability_score': openapi.Schema(type=openapi.TYPE_NUMBER),
                                'explanation': openapi.Schema(type=openapi.TYPE_STRING),
                            }
                        )
                    ),
                    'created_at': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME)
                }
            ),
            400: "Bad Request (e.g. User lacks a Risk Assessment or Market Data is missing)",
            500: "Internal ML Error"
        }
    )
    def post(self, request):
        try:
            recommendation = generate_fractional_portfolio(str(request.user.id))
            response_data = {
                "user_id": recommendation.user_id,
                "risk_summary": recommendation.risk_summary,
                "asset_allocation": recommendation.asset_allocation,
                "expected_return_1y": recommendation.expected_return_1y,
                "reasoning": recommendation.reasoning,
                "created_at": recommendation.created_at.isoformat()
            }
            return Response(response_data, status=status.HTTP_201_CREATED)
        except ValueError as e: return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e: return Response({"error": "An internal ML error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

