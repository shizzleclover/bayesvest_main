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


class PortfolioSimulationView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Run a personalized investment simulation using the user's actual portfolio assets and Prophet forecasts.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['initial_investment', 'monthly_contribution', 'years'],
            properties={
                'initial_investment': openapi.Schema(type=openapi.TYPE_NUMBER),
                'monthly_contribution': openapi.Schema(type=openapi.TYPE_NUMBER),
                'years': openapi.Schema(type=openapi.TYPE_INTEGER),
            },
        ),
        responses={200: "Simulation results", 400: "Bad input", 404: "No portfolio"},
    )
    def post(self, request):
        import math
        from apps.engine.models import Forecast
        from apps.market.models import Asset

        user_id = str(request.user.id)
        rec = Recommendation.objects(user_id=user_id).order_by('-created_at').first()
        if not rec:
            return Response({"error": "Generate a portfolio first"}, status=status.HTTP_404_NOT_FOUND)

        pv = float(request.data.get('initial_investment', 0))
        pmt = float(request.data.get('monthly_contribution', 0))
        years = int(request.data.get('years', 10))

        if pv <= 0:
            return Response({"error": "Initial investment must be positive"}, status=status.HTTP_400_BAD_REQUEST)
        if years < 1 or years > 50:
            return Response({"error": "Time horizon must be 1\u201350 years"}, status=status.HTTP_400_BAD_REQUEST)

        allocation = rec.asset_allocation or {}
        reasoning_map = {r.get('ticker'): r for r in (rec.reasoning or [])}

        asset_projections = []
        portfolio_return = 0.0
        portfolio_volatility = 0.0

        for ticker, weight in allocation.items():
            weight = float(weight)
            if weight <= 0:
                continue

            forecast = Forecast.objects(asset_ticker=ticker).first()
            asset_info = Asset.objects(ticker=ticker).first()
            reasoning = reasoning_map.get(ticker, {})

            exp_return = forecast.expected_return if forecast else reasoning.get('expected_return', 0.07)
            vol = forecast.volatility if forecast else reasoning.get('volatility', 0.15)

            asset_pv = pv * weight
            asset_pmt = pmt * weight

            optimistic_vals = _compound(asset_pv, asset_pmt, exp_return + vol, years)
            expected_vals = _compound(asset_pv, asset_pmt, exp_return, years)
            pessimistic_vals = _compound(asset_pv, asset_pmt, max(exp_return - vol, -0.5), years)

            total_contributed = asset_pv + (asset_pmt * 12 * years)

            asset_projections.append({
                'ticker': ticker,
                'name': (asset_info.name if asset_info else reasoning.get('asset_name', ticker)),
                'asset_class': (asset_info.asset_class if asset_info else reasoning.get('asset_class', '')),
                'weight': round(weight * 100, 1),
                'amount_invested': round(asset_pv, 2),
                'monthly_contribution': round(asset_pmt, 2),
                'expected_annual_return': round(exp_return * 100, 1),
                'volatility': round(vol * 100, 1),
                'total_contributed': round(total_contributed, 2),
                'optimistic_final': round(optimistic_vals[-1], 2),
                'expected_final': round(expected_vals[-1], 2),
                'pessimistic_final': round(pessimistic_vals[-1], 2),
                'expected_profit': round(expected_vals[-1] - total_contributed, 2),
                'suitability_score': reasoning.get('suitability_score'),
            })

            portfolio_return += weight * exp_return
            portfolio_volatility += weight * vol

        agg_opt = _compound(pv, pmt, portfolio_return + portfolio_volatility, years)
        agg_exp = _compound(pv, pmt, portfolio_return, years)
        agg_pes = _compound(pv, pmt, max(portfolio_return - portfolio_volatility, -0.5), years)

        total_contributed = pv + (pmt * 12 * years)

        return Response({
            'portfolio_expected_return': round(portfolio_return * 100, 1),
            'portfolio_volatility': round(portfolio_volatility * 100, 1),
            'total_contributed': round(total_contributed, 2),
            'years': years,
            'aggregate': {
                'optimistic': [round(v, 2) for v in agg_opt],
                'expected': [round(v, 2) for v in agg_exp],
                'pessimistic': [round(v, 2) for v in agg_pes],
            },
            'asset_projections': sorted(asset_projections, key=lambda a: a['weight'], reverse=True),
        })


def _compound(pv, pmt, annual_rate, years):
    monthly_rate = annual_rate / 12
    balance = pv
    points = [round(pv, 2)]
    for m in range(1, years * 12 + 1):
        balance = balance * (1 + monthly_rate) + pmt
        if m % 12 == 0:
            points.append(round(balance, 2))
    return points


def _serialize(recommendation):
    return {
        "user_id": recommendation.user_id,
        "risk_summary": recommendation.risk_summary,
        "asset_allocation": recommendation.asset_allocation,
        "expected_return_1y": recommendation.expected_return_1y,
        "reasoning": recommendation.reasoning,
        "created_at": recommendation.created_at.isoformat(),
    }
