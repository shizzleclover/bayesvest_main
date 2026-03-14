from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User, FinancialProfile, RiskAssessment
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

class RegisterView(APIView):
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        operation_description="Register a new Bayesvest User",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['email', 'password'],
            properties={
                'email': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_EMAIL),
                'password': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_PASSWORD)
            }
        ),
        responses={201: "Success", 400: "Bad Request"}
    )
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        if not email or not password: return Response({'error': 'Email and password required'}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects(email=email).first(): return Response({'error': 'Email already exists'}, status=status.HTTP_400_BAD_REQUEST)
        user = User(email=email)
        user.set_password(password)
        user.save()
        refresh = RefreshToken()
        refresh['user_id'] = str(user.id)
        return Response({'refresh': str(refresh), 'access': str(refresh.access_token), 'user': {'id': str(user.id), 'email': user.email}}, status=status.HTTP_201_CREATED)

class LoginView(APIView):
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        operation_description="Authenticate a Bayesvest User and receive a JWT",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['email', 'password'],
            properties={
                'email': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_EMAIL),
                'password': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_PASSWORD)
            }
        ),
        responses={200: "Success - JWT tokens returned", 401: "Unauthorized"}
    )
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        user = User.objects(email=email).first()
        if not user or not user.check_password(password): return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        refresh = RefreshToken()
        refresh['user_id'] = str(user.id)
        return Response({'refresh': str(refresh), 'access': str(refresh.access_token), 'user': {'id': str(user.id), 'email': user.email}}, status=status.HTTP_200_OK)

class FinancialProfileView(APIView):
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Get the user's Financial Profile",
        responses={200: "Success", 404: "Not Found"}
    )
    def get(self, request):
        profile = FinancialProfile.objects(user_id=str(request.user.id)).first()
        if not profile: return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'age': profile.age, 'income': profile.income, 'savings': profile.savings, 'goals': profile.goals, 'horizon': profile.horizon}, status=status.HTTP_200_OK)
        
    @swagger_auto_schema(
        operation_description="Create or update the user's Financial Profile",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'age': openapi.Schema(type=openapi.TYPE_INTEGER),
                'income': openapi.Schema(type=openapi.TYPE_NUMBER),
                'savings': openapi.Schema(type=openapi.TYPE_NUMBER),
                'goals': openapi.Schema(type=openapi.TYPE_STRING),
                'horizon': openapi.Schema(type=openapi.TYPE_STRING),
            }
        ),
        responses={200: "Profile Updated", 201: "Profile Created"}
    )
    def post(self, request):
        profile = FinancialProfile.objects(user_id=str(request.user.id)).first()
        if not profile: profile = FinancialProfile(user_id=str(request.user.id))
        
        profile.age = request.data.get('age', profile.age)
        profile.income = request.data.get('income', profile.income)
        profile.savings = request.data.get('savings', profile.savings)
        profile.goals = request.data.get('goals', profile.goals)
        profile.horizon = request.data.get('horizon', profile.horizon)
        profile.save()
        return Response({'status': 'Profile saved successfully'}, status=status.HTTP_200_OK)

class RiskAssessmentView(APIView):
    permission_classes = [IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Get the user's latest Risk Assessment",
        responses={200: "Success", 404: "Not Found"}
    )
    def get(self, request):
        assessment = RiskAssessment.objects(user_id=str(request.user.id)).order_by('-created_at').first()
        if not assessment: return Response({'error': 'No risk assessment found'}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            'answers': assessment.answers,
            'risk_score': assessment.risk_score,
            'raw_score': assessment.raw_score,
            'risk_level': assessment.risk_level,
            'created_at': assessment.created_at,
        }, status=status.HTTP_200_OK)
        
    @swagger_auto_schema(
        operation_description="Submit a new Risk Assessment. The AI Inference Engine processes these answers to compute a Baseline Risk Score (0 to 4) reflecting the user's capacity and tolerance for volatility.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['answers'],
            properties={
                'answers': openapi.Schema(
                    type=openapi.TYPE_OBJECT, 
                    description="The answers to the Bayesian questionnaire.",
                    required=['age_bracket', 'horizon', 'risk_tolerance', 'experience', 'income_stability', 'liquidity_needs', 'primary_goal', 'debt_to_income', 'dependents', 'reaction_to_volatility'],
                    properties={
                        'age_bracket': openapi.Schema(
                            type=openapi.TYPE_STRING, 
                            description="What is your current age bracket?",
                            enum=["18 - 25", "25 - 29", "30 - 45", "46 - 60", "60+"]
                        ),
                        'horizon': openapi.Schema(
                            type=openapi.TYPE_STRING, 
                            description="When do you expect to need significant access to this capital?",
                            enum=["Long-Term (10+ years)", "Medium-Term (3-10 years)", "Short-Term (0-3 years)"]
                        ),
                        'risk_tolerance': openapi.Schema(
                            type=openapi.TYPE_STRING, 
                            description="If your portfolio immediately dropped 20% in value due to a market correction, what would you do?",
                            enum=["Buy More", "Wait it out", "Panic Sell"]
                        ),
                        'experience': openapi.Schema(
                            type=openapi.TYPE_STRING, 
                            description="How would you rate your investment experience?",
                            enum=["Advanced (Derivatives/Crypto)", "Intermediate (Stocks/ETFs)", "Beginner (No experience)"]
                        ),
                        'income_stability': openapi.Schema(
                            type=openapi.TYPE_STRING, 
                            description="How stable is your current primary source of income?",
                            enum=["Highly Stable", "Variable / Freelance", "Unstable / Unemployed"]
                        ),
                        'liquidity_needs': openapi.Schema(
                            type=openapi.TYPE_STRING, 
                            description="Do you anticipate needing to withdraw a large portion of your investments in the near future?",
                            enum=["None", "Moderate", "High (May need cash soon)"]
                        ),
                        'primary_goal': openapi.Schema(
                            type=openapi.TYPE_STRING, 
                            description="What is the main objective of this portfolio?",
                            enum=["Aggressive Growth", "Balanced Wealth Accumulation", "Capital Preservation"]
                        ),
                        'debt_to_income': openapi.Schema(
                            type=openapi.TYPE_STRING, 
                            description="How would you describe your current debt levels relative to your income?",
                            enum=["Low (Comfortable)", "Moderate (Manageable)", "High (Strained)"]
                        ),
                        'dependents': openapi.Schema(
                            type=openapi.TYPE_STRING, 
                            description="How many dependents do you financially support?",
                            enum=["None", "1-2", "3+"]
                        ),
                        'reaction_to_volatility': openapi.Schema(
                            type=openapi.TYPE_STRING, 
                            description="Emotionally, how do you handle severe portfolio fluctuations?",
                            enum=["Excited by opportunity", "Slightly concerned but stay the course", "Anxious and want to sell"]
                        )
                    }
                )
            }
        ),
        responses={201: "Assessment Created", 400: "Bad Request"}
    )
    def post(self, request):
        answers = request.data.get('answers')
        if not answers or not isinstance(answers, dict):
            return Response({'error': 'Answers dictionary is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        from apps.engine.services.inference import bayes_engine, RISK_LABELS
        raw_score, band = bayes_engine.calculate_risk_score(answers)
        risk_level = RISK_LABELS.get(band, f"Level {band}")
        
        assessment = RiskAssessment(
            user_id=str(request.user.id),
            answers=answers,
            risk_score=band,
            raw_score=raw_score,
            risk_level=risk_level,
        )
        assessment.save()
        return Response({
            'status': 'Risk assessment processed successfully',
            'computed_risk_score': band,
            'raw_score': raw_score,
            'risk_level': risk_level,
        }, status=status.HTTP_201_CREATED)
