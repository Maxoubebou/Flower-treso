from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('reporting.urls')),            # dashboard à /, tva/ directement
    path('operations/', include('operations.urls')),
    path('finance/', include('finance.urls')),
    path('config/', include('config_app.urls')),
    path('budget/', include('budget.urls')),
]
