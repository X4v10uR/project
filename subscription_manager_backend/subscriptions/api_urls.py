from django.urls import path

from . import api_views, card_views, csv_import, planning

app_name = 'subscriptions_api'

urlpatterns = [
    path('calendar/', planning.calendar),
    path('calendar/export/', planning.calendar_export),
    path('insights/', planning.insights),
    path('review/', planning.review_inbox),
    path('review/action/', planning.review_action),
    path('settlements/', planning.settlements),
    path('settlements/<int:pk>/repay/', planning.repay),
    path('<int:pk>/renewal-comparison/', planning.renewal_comparison),
    path('<int:pk>/prices/', planning.price_changes),
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
