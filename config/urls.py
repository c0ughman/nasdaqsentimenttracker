"""
URL configuration for backend project.
"""
from django.contrib import admin
from django.urls import path, include

# Customize admin site
admin.site.site_header = "Nasdaq Sentiment Tracker Admin"
admin.site.site_title = "Nasdaq Admin Portal"
admin.site.index_title = "Welcome to Nasdaq Sentiment Tracker Administration"

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
]

