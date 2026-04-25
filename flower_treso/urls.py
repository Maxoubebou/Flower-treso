from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('reporting.urls')),            # dashboard à /, tva/ directement
    path('operations/', include('operations.urls')),
    path('finance/', include('finance.urls')),
    path('config/', include('config_app.urls')),
    path('budget/', include('budget.urls')),
    path('accounts/', include('allauth.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
