from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.home, name='home'),
    path('balance/adjust/', views.adjust_balance, name='adjust_balance'),
]
