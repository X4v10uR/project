from django.urls import path

from . import card_views, views

app_name = 'subscriptions'

urlpatterns = [
    path('', views.subscription_list, name='list'),
    path('export/csv/', views.subscription_export_csv, name='export_csv'),
    path('add/', views.subscription_create, name='create'),
    path('<int:pk>/edit/', views.subscription_update, name='update'),
    path('<int:pk>/delete/', views.subscription_delete, name='delete'),
    path('<int:pk>/offset/add/', views.add_reminder_offset, name='add_offset'),
    path('offset/<int:pk>/delete/', views.delete_reminder_offset, name='delete_offset'),
    path('<int:pk>/status/', views.update_subscription_status, name='update_status'),

    path('cards/', card_views.card_list, name='card_list'),
    path('cards/api/state/', card_views.cards_api_state, name='cards_api_state'),
    path('cards/api/create/', card_views.cards_api_create, name='cards_api_create'),
    path('cards/api/<int:pk>/update/', card_views.cards_api_update, name='cards_api_update'),
    path('cards/api/<int:pk>/set-primary/', card_views.cards_api_set_primary, name='cards_api_set_primary'),
    path('cards/api/<int:pk>/delete/', card_views.cards_api_delete, name='cards_api_delete'),
    path('cards/add/', card_views.card_create, name='card_create'),
    path('cards/<int:pk>/edit/', card_views.card_update, name='card_update'),
    path('cards/<int:pk>/delete/', card_views.card_delete, name='card_delete'),
]
