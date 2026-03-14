from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from .models import SavingsGoal


class GoalsListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        goals = SavingsGoal.objects(user_id=str(request.user.id)).order_by('-created_at')
        return Response([_serialize(g) for g in goals])

    @swagger_auto_schema(
        operation_description="Create a new savings goal.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['name', 'target_amount'],
            properties={
                'name': openapi.Schema(type=openapi.TYPE_STRING),
                'target_amount': openapi.Schema(type=openapi.TYPE_NUMBER),
                'current_amount': openapi.Schema(type=openapi.TYPE_NUMBER),
                'monthly_contribution': openapi.Schema(type=openapi.TYPE_NUMBER),
                'deadline': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME),
                'icon': openapi.Schema(type=openapi.TYPE_STRING),
            },
        ),
    )
    def post(self, request):
        data = request.data
        goal = SavingsGoal(
            user_id=str(request.user.id),
            name=data.get('name', ''),
            target_amount=float(data.get('target_amount', 0)),
            current_amount=float(data.get('current_amount', 0)),
            monthly_contribution=float(data.get('monthly_contribution', 0)),
            deadline=data.get('deadline'),
            icon=data.get('icon', 'savings'),
        )
        goal.save()
        return Response(_serialize(goal), status=status.HTTP_201_CREATED)


class GoalDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, goal_id):
        goal = SavingsGoal.objects(id=goal_id, user_id=str(request.user.id)).first()
        if not goal:
            return Response({"error": "Goal not found"}, status=status.HTTP_404_NOT_FOUND)

        data = request.data
        for field in ('name', 'target_amount', 'current_amount', 'monthly_contribution', 'deadline', 'icon'):
            if field in data:
                val = data[field]
                if field in ('target_amount', 'current_amount', 'monthly_contribution'):
                    val = float(val)
                setattr(goal, field, val)
        goal.save()
        return Response(_serialize(goal))

    def delete(self, request, goal_id):
        goal = SavingsGoal.objects(id=goal_id, user_id=str(request.user.id)).first()
        if not goal:
            return Response({"error": "Goal not found"}, status=status.HTTP_404_NOT_FOUND)
        goal.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _serialize(goal):
    return {
        "id": str(goal.id),
        "name": goal.name,
        "target_amount": goal.target_amount,
        "current_amount": goal.current_amount,
        "monthly_contribution": goal.monthly_contribution,
        "deadline": goal.deadline.isoformat() if goal.deadline else None,
        "icon": goal.icon,
        "created_at": goal.created_at.isoformat() if goal.created_at else None,
    }
