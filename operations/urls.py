from django.urls import path
from . import views

app_name = 'operations'

urlpatterns = [
    path('', views.process_list, name='process_list'),
    path('process/<int:operation_id>/', views.process_operation, name='process_operation'),
    path('ignore/<int:operation_id>/', views.operation_ignore, name='operation_ignore'),
    path('delete/<int:pk>/', views.operation_delete, name='operation_delete'),
]
