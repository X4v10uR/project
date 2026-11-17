from django.urls import path

from . import api_views, card_views, csv_import

app_name = 'subscriptions_api'

urlpatterns = [
    path('', api_views.subscriptions, name='list'),
    path('options/', api_views.subscription_options, name='options'),
    path('export/csv/', api_views.subscription_export, name='export'),
    path('import/csv/', csv_import.import_subscriptions, name='import'),
    path('<int:pk>/', api_views.subscription_detail, name='detail'),
    path('<int:pk>/status/', api_views.subscription_status, name='status'),
    path('<int:pk>/password/', api_views.subscription_password, name='password'),
    path('cards/', card_views.cards_collection, name='cards'),
    path('cards/<int:pk>/', card_views.card_detail, name='card_detail'),
    path('cards/<int:pk>/set-primary/', card_views.cards_api_set_primary, name='card_primary'),
]
