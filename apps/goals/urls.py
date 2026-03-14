from django.urls import path
from .views import GoalsListView, GoalDetailView

urlpatterns = [
    path('goals/', GoalsListView.as_view(), name='goals-list'),
    path('goals/<str:goal_id>/', GoalDetailView.as_view(), name='goal-detail'),
]
