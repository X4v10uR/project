from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'accounts'

urlpatterns = [
    path('signup/', views.signup, name='signup'),
    path('login/', auth_views.LoginView.as_view(template_name='accounts/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/accounts/login/'), name='logout'),
    path('settings/', views.settings, name='settings'),
    path('teams/', views.teams_overview, name='teams_overview'),
    path('teams/create/', views.team_create, name='team_create'),
    path('teams/<int:team_id>/', views.team_detail, name='team_detail'),
    path('teams/<int:team_id>/leave/', views.team_leave, name='team_leave'),
    path(
        'teams/<int:team_id>/members/<int:membership_id>/remove/',
        views.team_member_remove,
        name='team_member_remove',
    ),
    path('teams/<int:team_id>/delete/', views.team_delete, name='team_delete'),
    path('teams/<int:team_id>/invite/', views.team_invite, name='team_invite'),
    path(
        'teams/<int:team_id>/subscriptions/<int:subscription_id>/password/',
        views.team_subscription_password,
        name='team_subscription_password',
    ),
    path('invites/accept/<str:token>/', views.invite_accept, name='invite_accept'),
    path('teams/requests/<int:request_id>/approve/', views.team_request_approve, name='team_request_approve'),
    path('teams/requests/<int:request_id>/reject/', views.team_request_reject, name='team_request_reject'),
]
