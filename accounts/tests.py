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
