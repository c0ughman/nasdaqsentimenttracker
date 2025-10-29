#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from api.models import AnalysisRun
from django.utils import timezone
from datetime import timedelta

# Get all NASDAQ runs
nasdaq_runs = AnalysisRun.objects.filter(ticker__symbol='^IXIC').order_by('timestamp')

print('='*60)
print('NASDAQ COMPOSITE SENTIMENT DATA ANALYSIS')
print('='*60)

total_count = nasdaq_runs.count()
print(f'\nTotal AnalysisRuns: {total_count}')

if total_count == 0:
    print('\n⚠️  No data found! Run the sentiment analysis first.')
    exit()

# Get time range
first = nasdaq_runs.first()
last = nasdaq_runs.last()

print(f'\nOldest run: {first.timestamp}')
print(f'Newest run: {last.timestamp}')
print(f'Time span: {last.timestamp - first.timestamp}')

# Check recent data availability
cutoffs = [
    ('Last 1 minute', timedelta(minutes=1)),
    ('Last 5 minutes', timedelta(minutes=5)),
    ('Last 15 minutes', timedelta(minutes=15)),
    ('Last 30 minutes', timedelta(minutes=30)),
    ('Last 1 hour', timedelta(hours=1)),
    ('Last 4 hours', timedelta(hours=4)),
    ('Last 24 hours', timedelta(hours=24)),
]

print('\n' + '='*60)
print('DATA AVAILABILITY BY TIMEFRAME:')
print('='*60)

for label, delta in cutoffs:
    cutoff_time = timezone.now() - delta
    count = nasdaq_runs.filter(timestamp__gte=cutoff_time).count()
    print(f'{label:20s}: {count:4d} data points')

# Calculate average interval between runs
if total_count > 1:
    print('\n' + '='*60)
    print('RUN FREQUENCY ANALYSIS:')
    print('='*60)

    # Get last 20 runs to calculate average interval
    recent_runs = list(nasdaq_runs.order_by('-timestamp')[:20])
    recent_runs.reverse()

    intervals = []
    for i in range(1, len(recent_runs)):
        delta = recent_runs[i].timestamp - recent_runs[i-1].timestamp
        intervals.append(delta.total_seconds())

    if intervals:
        avg_interval = sum(intervals) / len(intervals)
        print(f'\nAverage interval between runs: {avg_interval:.1f} seconds ({avg_interval/60:.1f} minutes)')
        print(f'Minimum interval: {min(intervals):.1f} seconds')
        print(f'Maximum interval: {max(intervals):.1f} seconds')

# Show some recent runs
print('\n' + '='*60)
print('RECENT RUNS (Last 10):')
print('='*60)
for run in nasdaq_runs.order_by('-timestamp')[:10]:
    print(f'{run.timestamp.strftime("%Y-%m-%d %H:%M:%S")} | Score: {run.composite_score:+6.2f} | Articles: {run.articles_analyzed:3d}')

print('\n' + '='*60)
