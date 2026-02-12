from django.urls import path
from . import views

app_name = 'subscriptions'

urlpatterns = [
    path('', views.subscription_list, name='list'),
    path('add/', views.subscription_create, name='create'),
    path('<int:pk>/edit/', views.subscription_update, name='update'),
    path('<int:pk>/delete/', views.subscription_delete, name='delete'),
    path('<int:pk>/offset/add/', views.add_reminder_offset, name='add_offset'),
    path('offset/<int:pk>/delete/', views.delete_reminder_offset, name='delete_offset'),
    path('<int:pk>/status/', views.update_subscription_status, name='update_status'),
    
    # Card URLs
    path('cards/', views.card_list, name='card_list'),
    path('cards/add/', views.card_create, name='card_create'),
    path('cards/<int:pk>/edit/', views.card_update, name='card_update'),
    path('cards/<int:pk>/delete/', views.card_delete, name='card_delete'),
]
