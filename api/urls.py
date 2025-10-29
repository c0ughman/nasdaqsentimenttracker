from django.urls import path
from . import views

urlpatterns = [
    path('health/', views.health_check, name='health_check'),
    path('tickers/', views.available_tickers, name='available_tickers'),
    path('ticker/<str:ticker_symbol>/', views.ticker_analysis, name='ticker_analysis'),
    path('analysis-run/<int:run_id>/contributions/', views.analysis_run_contributions, name='analysis_run_contributions'),
    path('nasdaq/composite-score/', views.nasdaq_composite_score, name='nasdaq_composite_score'),
    path('nasdaq/historical-data/', views.nasdaq_historical_data, name='nasdaq_historical_data'),
    path('dashboard/', views.dashboard_data, name='dashboard_data'),  # New endpoint for nasdaq.html
    path('news/', views.news_articles, name='news_articles'),  # News articles endpoint for frontend
]
