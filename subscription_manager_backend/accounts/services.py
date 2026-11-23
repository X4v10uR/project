import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from subly.emailing import email_subject, frontend_url

from .models import TeamInvite, TeamMembership

logger = logging.getLogger(__name__)


def user_team_membership(user, team):
    if not user or not user.is_authenticated:
        return None
    return TeamMembership.objects.filter(user=user, team=team).first()


def is_team_member(user, team):
    return user_team_membership(user, team) is not None


def is_team_owner(user, team):
    membership = user_team_membership(user, team)
    return bool(membership and membership.role == TeamMembership.ROLE_OWNER)


def create_team_invite(*, team, email, role, invited_by, validity_hours=48):
    raw_token = secrets.token_urlsafe(32)
    token_hash = TeamInvite.hash_token(raw_token)
    expires_at = timezone.now() + timedelta(hours=validity_hours)
    invite = TeamInvite.objects.create(
        team=team,
        email=email.strip().lower(),
        role=role,
        invited_by=invited_by,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    return invite, raw_token


def invite_accept_url(raw_token):
    path = reverse("accounts:invite_accept", args=[raw_token])
    return frontend_url(path)


def send_team_invite_email(invite, raw_token):
    context = {
        "team": invite.team,
        "invite": invite,
        "invite_url": invite_accept_url(raw_token),
        "expires_at": invite.expires_at,
    }
    subject = email_subject("emails/team_invite_subject.txt", context)
    body = render_to_string("emails/team_invite.txt", context)
    html_body = render_to_string("emails/team_invite.html", context)
    sent = send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[invite.email],
        html_message=html_body,
        fail_silently=False,
    )
    if not sent:
        raise RuntimeError('Email backend did not send the invitation.')


def resolve_invite(raw_token):
    token_hash = TeamInvite.hash_token(raw_token)
    invite = TeamInvite.objects.select_related("team", "invited_by").filter(
        token_hash=token_hash
    ).first()
    return invite


def accept_invite(*, invite, user):
    membership, created = TeamMembership.objects.get_or_create(
        team=invite.team,
        user=user,
        defaults={
            "role": invite.role,
            "invited_by": invite.invited_by,
        },
    )
    if not created and membership.role != invite.role:
        membership.role = invite.role
        membership.save(update_fields=["role"])

    invite.accepted_by = user
    invite.accepted_at = timezone.now()
    invite.save(update_fields=["accepted_by", "accepted_at"])
    return membership
