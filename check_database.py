#!/usr/bin/env python
"""
Check which database is actually being used.
Run with: railway run python check_database.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
from django.db import connection
from django.contrib.auth.models import User

print('=' * 70)
print('DATABASE CONFIGURATION CHECK')
print('=' * 70)

# Check settings
print('\n1. Database settings:')
db_config = settings.DATABASES['default']
print(f'   Engine: {db_config.get("ENGINE", "Not set")}')
print(f'   Name: {db_config.get("NAME", "Not set")}')
print(f'   Host: {db_config.get("HOST", "Not set")}')
print(f'   Port: {db_config.get("PORT", "Not set")}')
print(f'   User: {db_config.get("USER", "Not set")}')

# Check actual connection
print('\n2. Actual database connection:')
with connection.cursor() as cursor:
    cursor.execute("SELECT version();")
    version = cursor.fetchone()
    print(f'   Database version: {version[0]}')

    # Get current database name
    cursor.execute("SELECT current_database();")
    db_name = cursor.fetchone()
    print(f'   Connected to database: {db_name[0]}')

    # Get connection info
    cursor.execute("SELECT inet_server_addr(), inet_server_port();")
    server_info = cursor.fetchone()
    print(f'   Server: {server_info[0]}:{server_info[1]}')

# Check users in THIS database
print('\n3. Users in the connected database:')
users = User.objects.all()
print(f'   Total users: {users.count()}')
for user in users:
    print(f'   - {user.username}: active={user.is_active}, staff={user.is_staff}, superuser={user.is_superuser}')

# Check environment variable
print('\n4. Environment DATABASE_URL:')
db_url = os.environ.get('DATABASE_URL', 'NOT SET')
if db_url != 'NOT SET':
    # Hide password for security
    if '@' in db_url:
        parts = db_url.split('@')
        user_part = parts[0].split('://')[1].split(':')[0]
        host_part = '@'.join(parts[1:])
        print(f'   DATABASE_URL: postgresql://{user_part}:****@{host_part}')
    else:
        print(f'   DATABASE_URL: {db_url}')
else:
    print(f'   DATABASE_URL: {db_url}')

print('\n' + '=' * 70)
