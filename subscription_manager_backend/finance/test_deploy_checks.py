from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.fernet import Fernet
from django.core.checks import Tags, run_checks
from django.test import SimpleTestCase, override_settings


@override_settings(
    SITE_URL='https://dues.example.test',
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
    ALLOWED_HOSTS=['dues.example.test'],
    ACCOUNT_PASSWORD_ENCRYPTION_KEY=Fernet.generate_key().decode('ascii'),
)
class DuesDeploymentTests(SimpleTestCase):
    def messages(self, include_deployment_checks=True):
        return {
            issue.id for issue in run_checks(tags=[Tags.security], include_deployment_checks=include_deployment_checks)
            if issue.id.startswith('dues.')
        }

    def test_disjoint_paths_pass_and_overlaps_are_deploy_errors(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            with override_settings(MEDIA_ROOT=base / 'public', STATIC_ROOT=base / 'static',
                                   STATICFILES_DIRS=[base / 'assets']):
                with override_settings(PRIVATE_MEDIA_ROOT=base / 'private'):
                    self.assertEqual(self.messages(), set())
                for private in (base, base / 'public', base / 'assets' / 'private'):
                    with self.subTest(private=private), override_settings(PRIVATE_MEDIA_ROOT=private):
                        self.assertEqual(self.messages(), {'dues.E001'})
                        self.assertEqual(self.messages(False), set())

    @override_settings(
        SITE_URL='https://dues.example.test/incorrect',
        SESSION_COOKIE_SECURE=False,
        ACCOUNT_PASSWORD_ENCRYPTION_KEY='',
        ALLOWED_HOSTS=['*'],
    )
    def test_actionable_checks_for_production_config(self):
        self.assertEqual(self.messages(), {'dues.W001', 'dues.W002', 'dues.W003', 'dues.W004'})

    @override_settings(ACCOUNT_PASSWORD_ENCRYPTION_KEY='synthetic-invalid-key')
    def test_bad_key_is_not_reported_as_a_valid_production_setting(self):
        self.assertEqual(self.messages(), {'dues.E002'})
