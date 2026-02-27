from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


class SignupViewTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_signup_get_renders_form(self):
        response = self.client.get(reverse('accounts:signup'))
        self.assertEqual(response.status_code, 200)

    def test_signup_valid_creates_user_and_logs_in(self):
        response = self.client.post(reverse('accounts:signup'), {
            'email': 'new@example.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })
        self.assertRedirects(response, reverse('dashboard:home'))
        self.assertTrue(User.objects.filter(email='new@example.com').exists())

    def test_signup_duplicate_email_fails(self):
        User.objects.create_user(email='dup@example.com', password='password')
        response = self.client.post(reverse('accounts:signup'), {
            'email': 'dup@example.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })
        self.assertEqual(response.status_code, 200)  # re-renders form
        self.assertEqual(User.objects.filter(email='dup@example.com').count(), 1)


class LoginLogoutTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='login@example.com', password='password')

    def test_login_page_renders(self):
        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code, 200)

    def test_login_valid_credentials(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': 'login@example.com',  # Django login uses 'username' field
            'password': 'password',
        })
        self.assertEqual(response.status_code, 302)

    def test_logout_redirects(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('accounts:logout'))
        self.assertEqual(response.status_code, 302)


class AuthRequiredTest(TestCase):
    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_subscription_list_requires_login(self):
        response = self.client.get(reverse('subscriptions:list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)


class SettingsViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='settings@example.com',
            password='OldStrongPass123!',
            first_name='Old',
            last_name='Name',
        )

    def test_settings_requires_login(self):
        response = self.client.get(reverse('accounts:settings'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_settings_get_renders_forms(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('accounts:settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Save profile')
        self.assertContains(response, 'Change password')

    def test_profile_settings_post_updates_user(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('accounts:settings'),
            {
                'form_type': 'profile',
                'first_name': 'New',
                'last_name': 'Display',
                'email': 'new-email@example.com',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('?updated=profile', response.url)

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'New')
        self.assertEqual(self.user.last_name, 'Display')
        self.assertEqual(self.user.email, 'new-email@example.com')

    def test_password_settings_post_changes_password_and_keeps_session(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('accounts:settings'),
            {
                'form_type': 'password',
                'old_password': 'OldStrongPass123!',
                'new_password1': 'NewStrongPass456!',
                'new_password2': 'NewStrongPass456!',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('?updated=password', response.url)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewStrongPass456!'))

        dashboard_response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(dashboard_response.status_code, 200)


class UserManagerTest(TestCase):
    def test_create_superuser_requires_staff_and_superuser_flags(self):
        with self.assertRaisesMessage(ValueError, 'Superuser must have is_staff=True.'):
            User.objects.create_superuser(
                email='badstaff@example.com',
                password='password',
                is_staff=False,
            )

        with self.assertRaisesMessage(ValueError, 'Superuser must have is_superuser=True.'):
            User.objects.create_superuser(
                email='badsuper@example.com',
                password='password',
                is_superuser=False,
            )
