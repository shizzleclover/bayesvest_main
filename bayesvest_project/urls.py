from django.urls import path, include
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

schema_view = get_schema_view(
   openapi.Info(
      title="Bayesvest API",
      default_version='v1',
      description="API documentation for the Bayesvest backend",
      terms_of_service="https://www.google.com/policies/terms/",
      contact=openapi.Contact(email="contact@bayesvest.ai"),
      license=openapi.License(name="BSD License"),
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path("api/users/", include("apps.users.urls")),
    path("api/", include("apps.portfolio.urls")),
    path("api/", include("apps.market.urls")),
]
