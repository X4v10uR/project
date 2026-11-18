import base64
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Generate a VAPID key pair to put in the server .env. Keep the private value secret.'

    def handle(self, *args, **options):
        key = ec.generate_private_key(ec.SECP256R1())
        public = key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        private = key.private_numbers().private_value.to_bytes(32, 'big')
        encode = lambda value: base64.urlsafe_b64encode(value).rstrip(b'=').decode()
        self.stdout.write('VAPID_PUBLIC_KEY=' + encode(public))
        self.stdout.write('VAPID_PRIVATE_KEY=' + encode(private))
