from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from apps.portfolio.services.portfolio_generator import generate_fractional_portfolio
from apps.portfolio.models import Recommendation
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi


class PortfolioGenerateView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Generate a personalized Bayesvest fractional portfolio based on the user's latest Risk Assessment.",
        responses={
            201: "Portfolio created",
            400: "Bad Request",
            500: "Internal ML Error",
        }
    )
    def post(self, request):
        try:
            recommendation = generate_fractional_portfolio(str(request.user.id))
            return Response(_serialize(recommendation), status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({"error": "An internal ML error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PortfolioLatestView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Retrieve the user's most recent portfolio recommendation.",
        responses={200: "Success", 404: "No portfolio found"},
    )
    def get(self, request):
        rec = Recommendation.objects(user_id=str(request.user.id)).order_by('-created_at').first()
        if not rec:
            return Response({"error": "No portfolio found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(_serialize(rec), status=status.HTTP_200_OK)


def _serialize(recommendation):
    return {
        "user_id": recommendation.user_id,
        "risk_summary": recommendation.risk_summary,
        "asset_allocation": recommendation.asset_allocation,
        "expected_return_1y": recommendation.expected_return_1y,
        "reasoning": recommendation.reasoning,
        "created_at": recommendation.created_at.isoformat(),
    }
