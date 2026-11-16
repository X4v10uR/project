from django.contrib.auth import views as auth_views
from django.conf import settings
from django.urls import path, reverse_lazy

from . import settings_views, views
from .forms import AccountPasswordResetForm

app_name = 'accounts'

urlpatterns = [
    path('signup/', views.signup, name='signup'),
    path('login/', auth_views.LoginView.as_view(template_name='accounts/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/accounts/login/'), name='logout'),
    path('password-reset/', auth_views.PasswordResetView.as_view(
        form_class=AccountPasswordResetForm,
        template_name='accounts/password_reset.html',
        email_template_name='emails/password_reset.txt',
        subject_template_name='emails/password_reset_subject.txt',
        extra_email_context={'site_url': settings.SITE_URL.rstrip('/')},
        success_url=reverse_lazy('accounts:password_reset_done'),
    ), name='password_reset'),
    path('password-reset/sent/', auth_views.PasswordResetDoneView.as_view(
        template_name='accounts/password_reset.html',
    ), name='password_reset_done'),
    path('password-reset/confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='accounts/password_reset.html',
        success_url=reverse_lazy('accounts:password_reset_complete'),
    ), name='password_reset_confirm'),
    path('password-reset/complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='accounts/password_reset.html',
    ), name='password_reset_complete'),
    path('settings/', settings_views.account_settings, name='settings'),
    path('settings/avatar/', settings_views.update_avatar, name='settings_avatar_update'),
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
