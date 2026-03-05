from django.db import migrations


def scrub_pending_request_passwords(apps, schema_editor):
    TeamSubscriptionRequest = apps.get_model("subscriptions", "TeamSubscriptionRequest")

    pending_requests = TeamSubscriptionRequest.objects.filter(status="pending")
    for pending_request in pending_requests.iterator():
        payload = pending_request.payload
        if not isinstance(payload, dict) or "account_password" not in payload:
            continue

        sanitized_payload = dict(payload)
        sanitized_payload.pop("account_password", None)
        pending_request.payload = sanitized_payload
        pending_request.save(update_fields=["payload", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0012_subscription_team_teamsubscriptionrequest_and_more"),
    ]

    operations = [
        migrations.RunPython(
            scrub_pending_request_passwords,
            migrations.RunPython.noop,
        ),
    ]
