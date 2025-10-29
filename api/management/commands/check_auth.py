"""
Django management command to check authentication setup
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.conf import settings


class Command(BaseCommand):
    help = 'Check authentication configuration and test login'

    def handle(self, *args, **options):
        self.stdout.write('=' * 70)
        self.stdout.write('AUTHENTICATION CHECK')
        self.stdout.write('=' * 70)

        # Check Django settings
        self.stdout.write('\n1. Django Settings:')
        self.stdout.write(f'   DEBUG: {settings.DEBUG}')
        self.stdout.write(f'   SESSION_COOKIE_SECURE: {settings.SESSION_COOKIE_SECURE if not settings.DEBUG else "False (DEBUG=True)"}')
        self.stdout.write(f'   CSRF_COOKIE_SECURE: {settings.CSRF_COOKIE_SECURE if not settings.DEBUG else "False (DEBUG=True)"}')
        self.stdout.write(f'   SESSION_COOKIE_SAMESITE: {settings.SESSION_COOKIE_SAMESITE}')
        self.stdout.write(f'   ALLOWED_HOSTS: {settings.ALLOWED_HOSTS}')
        self.stdout.write(f'   CSRF_TRUSTED_ORIGINS: {getattr(settings, "CSRF_TRUSTED_ORIGINS", "Not set")}')

        # Check database
        self.stdout.write('\n2. Database:')
        db = settings.DATABASES['default']
        self.stdout.write(f'   Engine: {db.get("ENGINE")}')
        self.stdout.write(f'   Name: {db.get("NAME")}')

        # List all users
        self.stdout.write('\n3. All users in database:')
        users = User.objects.all()
        self.stdout.write(f'   Total users: {users.count()}')
        for user in users:
            self.stdout.write(f'   - {user.username}: active={user.is_active}, staff={user.is_staff}, superuser={user.is_superuser}')

        # Test admin authentication
        self.stdout.write('\n4. Testing admin/admin123 authentication:')
        try:
            user = User.objects.get(username='admin')
            self.stdout.write(f'   User found: {user.username}')
            self.stdout.write(f'   Is active: {user.is_active}')
            self.stdout.write(f'   Is staff: {user.is_staff}')
            self.stdout.write(f'   Is superuser: {user.is_superuser}')

            # Test authentication
            auth_user = authenticate(username='admin', password='admin123')
            if auth_user:
                self.stdout.write(self.style.SUCCESS('   ✓ Authentication SUCCESSFUL!'))
            else:
                self.stdout.write(self.style.ERROR('   ✗ Authentication FAILED - password is incorrect'))
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR('   ✗ User "admin" does NOT exist'))

        self.stdout.write('\n' + '=' * 70)
