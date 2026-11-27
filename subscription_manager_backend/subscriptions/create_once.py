import json
import sqlite3
from collections.abc import Mapping
from uuid import UUID

from django.db import OperationalError, transaction
from django.http import QueryDict
from django.utils.crypto import constant_time_compare, salted_hmac
from rest_framework import serializers, status
from rest_framework.response import Response

from .models import SubscriptionCreationReceipt


def _request_digest(data):
    if not isinstance(data, Mapping):
        raise serializers.ValidationError('Submit subscription fields as an object.')
    # Normalize key order, but not array order or the actual values.
    values = dict(data.lists()) if isinstance(data, QueryDict) else dict(data)
    try:
        payload = json.dumps(values, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise serializers.ValidationError('Submit supported subscription form fields.') from exc
    # Do not store the payload, an account password, or an unkeyed password hash.
    return salted_hmac('dues.subscription.create', payload, algorithm='sha256').hexdigest()


def _is_sqlite_write_contention(exc):
    error = getattr(exc.__cause__, 'sqlite_errorcode', None)
    return error is not None and (error & 0xff) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)


def create_subscription_once(request, create, replay):
    raw_key = request.headers.get('Idempotency-Key')
    if raw_key is None:
        return create(request)
    try:
        key = UUID(raw_key) if len(raw_key) == 36 else None
    except ValueError:
        key = None
    if key is None or key.version != 4:
        raise serializers.ValidationError({'idempotency_key': 'Use a version 4 UUID.'})
    digest = _request_digest(request.data)
    try:
        with transaction.atomic():
            receipt, created = SubscriptionCreationReceipt.objects.get_or_create(
                user=request.user, key=key, defaults={'request_digest': digest},
            )
            if not created:
                if not constant_time_compare(receipt.request_digest, digest):
                    return Response({
                        'code': 'idempotency_conflict',
                        'detail': 'This save already completed with different details. Check your subscriptions before submitting again.',
                    }, status=status.HTTP_409_CONFLICT)
                return replay(request, receipt)

            # Receipt creation, subscription/request, and any same-day charge commit together.
            result = create(request)
            if result.status_code == status.HTTP_201_CREATED:
                receipt.subscription_id = result.data['id']
            elif result.status_code == status.HTTP_202_ACCEPTED:
                receipt.team_request_id = result.data['request_id']
            else:
                raise RuntimeError('Unexpected result when creating a keyed subscription.')
            receipt.response_status = result.status_code
            receipt.save(update_fields=['response_status', 'subscription', 'team_request'])
            return result
    except OperationalError as exc:
        if not _is_sqlite_write_contention(exc):
            raise
        return Response(
            {'detail': 'Another save is in progress. Retry with the same key.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE, headers={'Retry-After': '1'},
        )
