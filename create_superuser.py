#!/usr/bin/env python
"""
Script to create a superuser in the Railway database.
Run with: railway run python create_superuser.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User

username = 'admin'
email = 'admin@example.com'
password = 'admin123'

# Delete existing admin user if it exists
User.objects.filter(username=username).delete()

# Create new superuser
user = User.objects.create_superuser(username=username, email=email, password=password)
print(f'✓ Superuser created successfully!')
print(f'  Username: {username}')
print(f'  Password: {password}')
print(f'  Email: {email}')
print(f'  Is superuser: {user.is_superuser}')
print(f'  Is active: {user.is_active}')
print(f'  User ID: {user.id}')
print(f'\nTotal users in database: {User.objects.count()}')
print(f'All users: {list(User.objects.values_list("username", "is_superuser", "is_active"))}')
