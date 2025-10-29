#!/usr/bin/env python
"""
Test the exact admin login flow to see where it fails.
Run with: railway run python test_admin_login.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.admin.sites import site as admin_site

print('=' * 70)
print('ADMIN LOGIN DIAGNOSTIC TEST')
print('=' * 70)

# Get the admin user
username = 'admin'
password = 'admin123'

print(f'\n1. Testing with username: {username}')
print(f'   Password: {password}')

# Check if user exists
try:
    user = User.objects.get(username=username)
    print(f'\n2. User found in database:')
    print(f'   - username: {user.username}')
    print(f'   - is_active: {user.is_active}')
    print(f'   - is_staff: {user.is_staff}')
    print(f'   - is_superuser: {user.is_superuser}')
except User.DoesNotExist:
    print(f'\n✗ ERROR: User "{username}" does not exist!')
    exit(1)

# Test authentication
print(f'\n3. Testing Django authentication:')
auth_user = authenticate(username=username, password=password)
if auth_user:
    print(f'   ✓ Authentication successful')
else:
    print(f'   ✗ Authentication FAILED')
    print(f'   This means the password is incorrect or authentication backend has an issue')
    exit(1)

# Check if user has permission to access admin
print(f'\n4. Checking admin access permissions:')
print(f'   - has_perm("admin"): {user.has_perm("admin")}')
print(f'   - has_module_perms("admin"): {user.has_module_perms("admin")}')

# Check admin site configuration
print(f'\n5. Admin site check:')
print(f'   - Admin site: {admin_site}')
print(f'   - Has staff permission: {user.is_active and user.is_staff}')

# The critical check Django admin uses
if not (user.is_active and user.is_staff):
    print(f'\n   ✗ PROBLEM FOUND!')
    print(f'   User needs BOTH is_active=True AND is_staff=True')
    print(f'   Current: is_active={user.is_active}, is_staff={user.is_staff}')
else:
    print(f'   ✓ User has correct permissions for admin access')

# Check session settings that affect login
print(f'\n6. Session and Cookie Settings:')
from django.conf import settings
print(f'   - DEBUG: {settings.DEBUG}')
print(f'   - SESSION_COOKIE_SECURE: {settings.SESSION_COOKIE_SECURE if not settings.DEBUG else "False (DEBUG=True)"}')
print(f'   - CSRF_COOKIE_SECURE: {settings.CSRF_COOKIE_SECURE if not settings.DEBUG else "False (DEBUG=True)"}')
print(f'   - SESSION_COOKIE_SAMESITE: {settings.SESSION_COOKIE_SAMESITE}')
print(f'   - SECURE_PROXY_SSL_HEADER: {getattr(settings, "SECURE_PROXY_SSL_HEADER", "Not set")}')

# Test the actual admin has_permission method
print(f'\n7. Testing admin_site.has_permission():')
from django.test import RequestFactory
factory = RequestFactory()
request = factory.get('/admin/')
request.user = user
has_permission = admin_site.has_permission(request)
print(f'   - has_permission result: {has_permission}')

if not has_permission:
    print(f'\n   ✗ PROBLEM: admin_site.has_permission() returned False!')
    print(f'   This is why login fails.')
else:
    print(f'   ✓ Permission check passed')

print('\n' + '=' * 70)
print('DIAGNOSIS COMPLETE')
print('=' * 70)
