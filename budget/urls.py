from django.urls import path
from . import views

app_name = 'budget'

urlpatterns = [
    path('', views.budget_dashboard, name='dashboard'),
    path('item/update/<int:pk>/', views.budget_item_update, name='item_update'),
    path('subcategory/add/', views.add_subcategory, name='add_subcategory'),
    path('subcategory/delete/<int:pk>/', views.delete_subcategory, name='delete_subcategory'),
    path('line/add/', views.add_budget_line, name='add_line'),
    path('line/delete/<int:pk>/', views.delete_line, name='delete_line'),
    path('ligne-budgetaire/delete/<int:pk>/', views.delete_ligne_budgetaire, name='delete_ligne_budgetaire'),
    path('subcategory/move/<int:pk>/<str:direction>/', views.move_subcategory, name='move_subcategory'),
    path('subcategory/reorder/', views.reorder_categories, name='reorder_categories'),
]
