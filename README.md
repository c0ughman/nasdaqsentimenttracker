# Django Backend

This is the backend API for the application built with Django and Django REST Framework.

## Quick Start

1. **Set up PostgreSQL database** (run from project root):
```bash
# macOS/Linux
./setup_database.sh

# Windows
.\setup_database.ps1
```

2. **Create and activate virtual environment**:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
```

4. **Run migrations**:
```bash
python manage.py migrate
```

5. **Create superuser**:
```bash
python manage.py createsuperuser
```

6. **Start server**:
```bash
python manage.py runserver
```

Access admin at: http://localhost:8000/admin/

## Project Structure

- `config/` - Django project configuration
- `api/` - Main API application
- `manage.py` - Django management script

## Available Commands

- `python manage.py runserver` - Start development server
- `python manage.py makemigrations` - Create new migrations
- `python manage.py migrate` - Apply migrations
- `python manage.py createsuperuser` - Create admin user
- `python manage.py test` - Run tests
- `python manage.py collectstatic` - Collect static files for production

## API Endpoints

- `/api/health/` - Health check endpoint
- `/admin/` - Django admin interface

## Environment Variables

Create a `.env` file in the backend directory:

```
DJANGO_SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

## Production Deployment

1. Set `DEBUG=False` in environment variables
2. Set a strong `DJANGO_SECRET_KEY`
3. Configure `ALLOWED_HOSTS` with your domain
4. Use PostgreSQL or another production database
5. Collect static files: `python manage.py collectstatic`
6. Use Gunicorn: `gunicorn config.wsgi:application`

## Adding New Endpoints

1. Create views in `api/views.py`
2. Add URL patterns in `api/urls.py`
3. Create serializers if needed
4. Add models in `api/models.py` if needed
5. Run migrations if you added models

