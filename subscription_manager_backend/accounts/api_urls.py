from django.urls import path

from . import api_views as views

app_name = 'accounts_api'

urlpatterns = [
    path('session/', views.SessionView.as_view(), name='session'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('signup/', views.SignupView.as_view(), name='signup'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('settings/', views.SettingsView.as_view(), name='settings'),
    path('settings/avatar/', views.AvatarView.as_view(), name='avatar'),
    path('settings/<str:section>/', views.SettingsSectionView.as_view(), name='settings_section'),
    path('teams/', views.TeamsView.as_view(), name='teams'),
    path('teams/<int:team_id>/', views.TeamDetailView.as_view(), name='team_detail'),
    path('teams/<int:team_id>/members/<int:membership_id>/', views.TeamMemberView.as_view(), name='team_member'),
    path('teams/<int:team_id>/leave/', views.TeamLeaveView.as_view(), name='team_leave'),
    path('teams/<int:team_id>/invite/', views.TeamInviteView.as_view(), name='team_invite'),
    path(
        'teams/<int:team_id>/subscriptions/<int:subscription_id>/password/',
        views.TeamSubscriptionPasswordView.as_view(),
        name='team_subscription_password',
    ),
    path('teams/requests/<int:request_id>/<str:action>/', views.TeamRequestReviewView.as_view(), name='request_review'),
    path('invites/accept/<str:token>/', views.AcceptInviteView.as_view(), name='invite_accept'),
]
