#!/usr/bin/env python
"""
Script to test if authentication works in Railway database.
Run with: railway run python test_login.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import authenticate
from django.contrib.auth.models import User

# Test credentials
test_users = [
    ('admin', 'admin123'),
    ('emmanuel', None),  # We don't know the password
]

print('=' * 60)
print('AUTHENTICATION TEST')
print('=' * 60)

# First, list all users
print('\nAll users in database:')
for user in User.objects.all():
    print(f'  - {user.username}: active={user.is_active}, superuser={user.is_superuser}, staff={user.is_staff}')

# Test authentication
print('\n\nTesting authentication for admin/admin123:')
user = authenticate(username='admin', password='admin123')
if user is not None:
    print(f'✓ Authentication SUCCESSFUL for admin!')
    print(f'  User: {user.username}')
    print(f'  Is active: {user.is_active}')
    print(f'  Is superuser: {user.is_superuser}')
    print(f'  Is staff: {user.is_staff}')
else:
    print('✗ Authentication FAILED for admin/admin123')
    print('  Checking if user exists...')
    try:
        user = User.objects.get(username='admin')
        print(f'  User exists: {user.username}')
        print(f'  Is active: {user.is_active}')
        print(f'  Is staff: {user.is_staff}')
        print(f'  Password hash: {user.password[:50]}...')
    except User.DoesNotExist:
        print('  User does NOT exist!')

# Check Django settings
print('\n\nDjango Settings:')
from django.conf import settings
print(f'  DEBUG: {settings.DEBUG}')
print(f'  ALLOWED_HOSTS: {settings.ALLOWED_HOSTS}')
print(f'  SESSION_ENGINE: {settings.SESSION_ENGINE}')
print(f'  SESSION_COOKIE_SECURE: {getattr(settings, "SESSION_COOKIE_SECURE", "Not set")}')
print(f'  CSRF_COOKIE_SECURE: {getattr(settings, "CSRF_COOKIE_SECURE", "Not set")}')

print('\n' + '=' * 60)
