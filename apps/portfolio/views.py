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


class PortfolioHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="List all portfolio recommendations for the user.",
        responses={200: "Success"},
    )
    def get(self, request):
        recs = Recommendation.objects(user_id=str(request.user.id)).order_by('-created_at')
        return Response([_serialize(r) for r in recs], status=status.HTTP_200_OK)


class PortfolioDriftView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Check how much the user's current portfolio has drifted from what the engine would recommend now.",
        responses={200: "Success", 404: "No portfolio found"},
    )
    def get(self, request):
        user_id = str(request.user.id)
        current = Recommendation.objects(user_id=user_id).order_by('-created_at').first()
        if not current:
            return Response({"error": "No portfolio found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            from apps.engine.services.inference import bayes_engine, RISK_LABELS
            from apps.users.models import RiskAssessment
            ra = RiskAssessment.objects(user_id=user_id).order_by('-created_at').first()
            if not ra:
                return Response({"drift_pct": 0, "should_rebalance": False})

            raw_score, band = bayes_engine.calculate_risk_score(ra.answers)
            risk_label = RISK_LABELS.get(band, "Unknown")

            old_alloc = current.asset_allocation or {}
            total_drift = 0.0
            tickers = set(list(old_alloc.keys()))

            for t in tickers:
                old_w = old_alloc.get(t, 0)
                total_drift += abs(old_w)

            avg_drift = total_drift / max(len(tickers), 1) * 100

            should_rebalance = avg_drift > 5 or (
                hasattr(ra, 'raw_score') and ra.raw_score and
                abs(ra.raw_score - raw_score) > 10
            )

            return Response({
                "drift_pct": round(avg_drift, 1),
                "should_rebalance": should_rebalance,
                "current_risk": risk_label,
                "current_score": raw_score,
                "portfolio_age_days": (
                    __import__('datetime').datetime.utcnow() - current.created_at
                ).days if current.created_at else 0,
            })
        except Exception as e:
            return Response({"drift_pct": 0, "should_rebalance": False, "error": str(e)})


def _serialize(recommendation):
    return {
        "user_id": recommendation.user_id,
        "risk_summary": recommendation.risk_summary,
        "asset_allocation": recommendation.asset_allocation,
        "expected_return_1y": recommendation.expected_return_1y,
        "reasoning": recommendation.reasoning,
        "created_at": recommendation.created_at.isoformat(),
    }
