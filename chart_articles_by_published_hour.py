#!/usr/bin/env python3
"""
Chart showing news articles by published hour
"""

import json
import os
from datetime import datetime, timedelta
from collections import defaultdict
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pytz

# Find the most recent export file
data_dir = './data_exports'
export_files = [f for f in os.listdir(data_dir) if f.startswith('news_articles_last_3_0_hours') and f.endswith('.json')]
if not export_files:
    print("❌ No export file found!")
    exit(1)

latest_file = sorted(export_files)[-1]
filepath = os.path.join(data_dir, latest_file)

print(f"📊 Loading: {latest_file}")

# Load data
with open(filepath, 'r') as f:
    articles = json.load(f)

print(f"Total articles: {len(articles)}\n")

# Convert to EST for display
est_tz = pytz.timezone('America/New_York')
utc_tz = pytz.UTC

# Group articles by published hour
articles_by_hour = defaultdict(int)
hour_details = defaultdict(list)

for article in articles:
    published_at_str = article.get('published_at', '')
    if not published_at_str:
        continue
    
    try:
        published_at = datetime.fromisoformat(published_at_str.replace('Z', '+00:00'))
        if published_at.tzinfo is None:
            published_at = utc_tz.localize(published_at)
        
        # Convert to EST
        published_at_est = published_at.astimezone(est_tz)
        
        # Round down to the hour
        hour_key = published_at_est.replace(minute=0, second=0, microsecond=0)
        
        articles_by_hour[hour_key] += 1
        hour_details[hour_key].append({
            'headline': article.get('headline', '')[:60],
            'ticker': article.get('ticker', 'N/A'),
            'source': article.get('source', 'N/A'),
            'published_at': published_at_est.isoformat()
        })
    except Exception as e:
        print(f"Error parsing published_at '{published_at_str}': {e}")
        continue

if not articles_by_hour:
    print("❌ No articles with published_at timestamps found!")
    exit(1)

# Sort hours
sorted_hours = sorted(articles_by_hour.keys())
min_hour = sorted_hours[0]
max_hour = sorted_hours[-1]

print(f"Date range: {min_hour.strftime('%Y-%m-%d %H:00')} to {max_hour.strftime('%Y-%m-%d %H:00')} EST")
print(f"Total hours: {len(sorted_hours)}\n")

# Create chart
fig, ax = plt.subplots(figsize=(20, 8))

# Prepare data
hours = sorted_hours
counts = [articles_by_hour[h] for h in hours]

# Create bar chart
bars = ax.bar(range(len(hours)), counts, color='steelblue', alpha=0.7, edgecolor='black', linewidth=0.5)

# Customize x-axis
ax.set_xlabel('Published Hour (EST)', fontsize=12, fontweight='bold')
ax.set_ylabel('Number of Articles', fontsize=12, fontweight='bold')
ax.set_title(f'News Articles Published by Hour\n{min_hour.strftime("%Y-%m-%d %H:00")} to {max_hour.strftime("%Y-%m-%d %H:00")} EST | Total: {sum(counts)} articles', 
             fontsize=14, fontweight='bold', pad=20)

# Set x-axis labels (show every hour, rotate for readability)
if len(hours) <= 24:
    # Show all hours if <= 24
    ax.set_xticks(range(len(hours)))
    ax.set_xticklabels([h.strftime('%m/%d\n%H:00') for h in hours], rotation=45, ha='right', fontsize=9)
else:
    # Show every Nth hour if more than 24
    step = max(1, len(hours) // 24)
    ax.set_xticks(range(0, len(hours), step))
    ax.set_xticklabels([hours[i].strftime('%m/%d\n%H:00') for i in range(0, len(hours), step)], 
                       rotation=45, ha='right', fontsize=9)

# Add grid
ax.grid(True, alpha=0.3, linestyle='--', axis='y')
ax.set_axisbelow(True)

# Add value labels on bars (if not too many)
if len(hours) <= 48:
    for i, (bar, count) in enumerate(zip(bars, counts)):
        if count > 0:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{int(count)}',
                   ha='center', va='bottom', fontsize=8, fontweight='bold')

# Add summary statistics
total_articles = sum(counts)
max_count = max(counts)
max_hour_idx = counts.index(max_count)
max_hour_time = hours[max_hour_idx]

stats_text = (
    f'Total Articles: {total_articles}\n'
    f'Peak Hour: {max_hour_time.strftime("%Y-%m-%d %H:00")} EST ({max_count} articles)\n'
    f'Hours with Articles: {len([c for c in counts if c > 0])}/{len(hours)}'
)

ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
        fontsize=10, verticalalignment='top',
        bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

# Adjust layout
plt.tight_layout()

# Save chart
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
output_file = f'{data_dir}/articles_by_published_hour_{timestamp}.png'
plt.savefig(output_file, dpi=150, bbox_inches='tight')
print(f"✅ Chart saved: {output_file}")

# Print summary by hour
print("\n" + "=" * 80)
print("📊 ARTICLES BY PUBLISHED HOUR (EST)")
print("=" * 80)
print(f"{'Hour':<20} {'Count':<10} {'Sample Articles'}")
print("-" * 80)

for hour in sorted_hours[:20]:  # Show first 20 hours
    count = articles_by_hour[hour]
    samples = hour_details[hour][:3]  # First 3 articles
    sample_text = ", ".join([f"{s['ticker']}: {s['headline'][:30]}..." for s in samples])
    print(f"{hour.strftime('%Y-%m-%d %H:00'):<20} {count:<10} {sample_text}")

if len(sorted_hours) > 20:
    print(f"\n... and {len(sorted_hours) - 20} more hours")

plt.show()

