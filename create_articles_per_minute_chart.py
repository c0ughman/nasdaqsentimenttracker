#!/usr/bin/env python3
"""
Create a bar chart showing articles per minute from yesterday to today
"""

import json
import os
from datetime import datetime, timedelta
from collections import defaultdict
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from dateutil import parser
import pytz

# Find the most recent news articles export file
data_exports_dir = './data_exports'
json_files = [f for f in os.listdir(data_exports_dir) if f.startswith('news_articles_last_') and f.endswith('.json')]

if not json_files:
    print("❌ No news articles JSON file found in data_exports/")
    exit(1)

# Get the most recent file
latest_file = sorted(json_files)[-1]
file_path = os.path.join(data_exports_dir, latest_file)
print(f"📂 Reading: {file_path}")

# Load the data
with open(file_path, 'r', encoding='utf-8') as f:
    articles = json.load(f)

print(f"📰 Loaded {len(articles)} articles")

# Timezone conversion: UTC to EST
UTC = pytz.UTC
EST = pytz.timezone('America/New_York')  # Automatically handles EST/EDT

# Group articles by minute (using fetched_at, converted to EST)
articles_by_minute = defaultdict(int)

for article in articles:
    fetched_at_str = article.get('fetched_at')
    if not fetched_at_str:
        continue
    
    # Parse the datetime string
    try:
        fetched_at = parser.parse(fetched_at_str)
        
        # Ensure timezone-aware (assume UTC if naive)
        if fetched_at.tzinfo is None:
            fetched_at = UTC.localize(fetched_at)
        
        # Convert UTC to EST
        fetched_at_est = fetched_at.astimezone(EST)
        
        # Round down to the minute
        minute_key = fetched_at_est.replace(second=0, microsecond=0)
        articles_by_minute[minute_key] += 1
    except Exception as e:
        print(f"⚠️  Error parsing date '{fetched_at_str}': {e}")
        continue

if not articles_by_minute:
    print("❌ No valid timestamps found")
    exit(1)

# Get date range
all_minutes = sorted(articles_by_minute.keys())
start_time = all_minutes[0]
end_time = all_minutes[-1]

# Use the latest article time as "now" reference (already in EST from conversion above)
now = end_time
if now.tzinfo is None:
    # If somehow still naive, assume EST
    now = EST.localize(now)

# Calculate yesterday and today boundaries (in EST)
yesterday = (now - timedelta(days=1)).date()
today = now.date()

# Generate 15-minute chunks for both days - full days with no gap removal
from datetime import time as dt_time
chunks = []  # List of (chunk_start_time, total_count)

# Generate ALL 15-minute chunks for yesterday (0:00 to 23:45) - full 24 hours in EST
yesterday_start = EST.localize(datetime.combine(yesterday, dt_time(0, 0)))

for hour in range(24):  # 0:00 to 23:59 - ALL hours
    for quarter in range(4):  # 0, 15, 30, 45 minutes
        chunk_start = yesterday_start.replace(hour=hour, minute=quarter * 15, second=0, microsecond=0)
        
        # Sum all articles in this 15-minute chunk
        chunk_count = 0
        for minute_offset in range(15):
            minute_dt = chunk_start + timedelta(minutes=minute_offset)
            chunk_count += articles_by_minute.get(minute_dt, 0)
        
        chunks.append((chunk_start, chunk_count))

# Generate 15-minute chunks for today (0:00 to 15:45) - up to 4pm in EST
today_start = EST.localize(datetime.combine(today, dt_time(0, 0)))

for hour in range(16):  # 0:00 to 15:59 - up to 4pm
    for quarter in range(4):  # 0, 15, 30, 45 minutes
        chunk_start = today_start.replace(hour=hour, minute=quarter * 15, second=0, microsecond=0)
        
        # Sum all articles in this 15-minute chunk
        chunk_count = 0
        for minute_offset in range(15):
            minute_dt = chunk_start + timedelta(minutes=minute_offset)
            chunk_count += articles_by_minute.get(minute_dt, 0)
        
        chunks.append((chunk_start, chunk_count))

# Extract minutes and counts from chunks
minutes = [chunk[0] for chunk in chunks]
counts = [chunk[1] for chunk in chunks]

# Create the chart with larger figure size
fig, ax = plt.subplots(figsize=(24, 10))

# Create x-axis positions - no gap removal, show all chunks
x_positions = []
x_labels = []
x_label_positions = []
day_break_position = None
yesterday_minutes = []
today_minutes = []

# Find where yesterday ends and today begins
yesterday_end_idx = None
for i, minute in enumerate(minutes):
    if minute.date() == today:
        yesterday_end_idx = i
        break

for i, minute in enumerate(minutes):
    # Sequential position (all chunks included, no gap removal)
    x_positions.append(i)
    
    minute_date = minute.date()
    minute_hour = minute.hour
    minute_min = minute.minute
    
    # Track day separation
    if minute_date == yesterday:
        yesterday_minutes.append(i)
    elif minute_date == today:
        today_minutes.append(i)
        # Mark the transition point (first today chunk)
        if yesterday_end_idx is not None and i == yesterday_end_idx:
            day_break_position = i - 0.5
    
    # Create label for 15-minute chunks
    # Show label for every chunk (every 15 minutes)
    # Format: full date+time for hour boundaries, just time for others
    if minute_min == 0:  # Hour boundary
        label = f"{minute_date.strftime('%m/%d')} {minute_hour:02d}:00"
    else:
        label = f"{minute_hour:02d}:{minute_min:02d}"
    
    x_labels.append(label)
    x_label_positions.append(i)

# Use all counts (no filtering)
filtered_counts = counts

# Track which bars exceed 20 for annotation
truncated_bars = []
max_truncated = 0
for i, count in enumerate(filtered_counts):
    if count > 20:
        truncated_bars.append((i, count))
        max_truncated = max(max_truncated, count)

# Print summary
print(f"📊 Creating chart for {len(minutes)} 15-minute chunks (using fetched_at)")
print(f"   Yesterday: 96 chunks (0:00-23:45)")
print(f"   Today: 64 chunks (0:00-15:45)")
print(f"   Date range: {minutes[0].date()} to {minutes[-1].date()}")
print(f"   Total articles: {sum(filtered_counts)}")
print(f"   Max articles per chunk: {max(filtered_counts) if filtered_counts else 0}")
if truncated_bars:
    print(f"   Chunks truncated (>20): {len(truncated_bars)} (max: {max_truncated})")

# Truncate counts at 20 for display
display_counts = [min(c, 20) for c in filtered_counts]

# Create bar chart with compressed x-axis
bar_width = 0.9

# Color bars: normal (blue), truncated (red)
colors = ['steelblue' if c <= 20 else 'crimson' for c in filtered_counts]
bars = ax.bar(x_positions, display_counts, width=bar_width, align='center', 
              color=colors, edgecolor='white', linewidth=0.5, alpha=0.8)

# Add day separation background
if yesterday_minutes and today_minutes:
    # Background color for yesterday (light blue)
    if yesterday_minutes:
        y_start = min(yesterday_minutes) - 0.5
        y_end = max(yesterday_minutes) + 0.5
        ax.axvspan(y_start, y_end, alpha=0.1, color='blue', label=f'Yesterday ({yesterday})')
    
    # Background color for today (light green)
    if today_minutes:
        t_start = min(today_minutes) - 0.5
        t_end = max(today_minutes) + 0.5
        ax.axvspan(t_start, t_end, alpha=0.1, color='green', label=f'Today ({today})')

# Add thick vertical line at day break
if day_break_position is not None:
    ax.axvline(x=day_break_position, color='red', linestyle='-', linewidth=3, alpha=0.8, zorder=10)
    # Add text annotation
    ax.text(day_break_position, ax.get_ylim()[1] * 0.98, 'DAY BREAK', 
            ha='center', va='top', fontsize=11, fontweight='bold', color='darkred', 
            bbox=dict(boxstyle='round,pad=0.5', facecolor='yellow', alpha=0.9, edgecolor='red', linewidth=2),
            zorder=11)

# Add annotations for truncated bars
if truncated_bars:
    for idx, actual_count in truncated_bars:
        # Add annotation at top of truncated bar
        ax.annotate(f'{actual_count}', 
                   xy=(x_positions[idx], 20), 
                   xytext=(x_positions[idx], 22.5),
                   ha='center', va='bottom',
                   fontsize=9, fontweight='bold',
                   color='crimson',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.9, edgecolor='crimson'),
                   arrowprops=dict(arrowstyle='->', color='crimson', lw=2, alpha=0.8))

# Set y-axis limit to 20 with padding for annotations
ax.set_ylim(0, 25)

# Set x-axis with compressed positions
ax.set_xlim(-0.5, len(x_positions) - 0.5)
ax.set_xticks(x_label_positions)
ax.set_xticklabels(x_labels, rotation=45, ha='right', fontsize=9)

# Add minor ticks for every minute (but don't label them)
ax.set_xticks(range(len(x_positions)), minor=True)
ax.tick_params(which='minor', length=2, width=0.5)

# Set labels and title
ax.set_xlabel('Time (Date Hour:Minute EST) - 15-Minute Chunks (Fetched At)', fontsize=13, fontweight='bold', labelpad=15)
ax.set_ylabel('Number of Articles per 15-Minute Chunk (Truncated at 20)', fontsize=13, fontweight='bold', labelpad=15)
title = f'News Articles Per 15-Minute Chunk (Fetched At, EST) - {yesterday} to {today}\nTotal: {sum(filtered_counts)} articles | {len(minutes)} chunks'
if truncated_bars:
    title += f' | {len(truncated_bars)} chunks >20 (annotated)'
ax.set_title(title, fontsize=16, fontweight='bold', pad=25)

# Add grid for easier reading
ax.grid(True, alpha=0.3, linestyle='--', axis='y', linewidth=0.8)
ax.grid(True, alpha=0.15, linestyle=':', axis='x', linewidth=0.5, which='minor')
ax.set_axisbelow(True)

# Add statistics text box
stats_text = f'Total Articles: {sum(filtered_counts)}\n'
stats_text += f'Max/Min: {max(filtered_counts)}/{min(filtered_counts)}\n'
stats_text += f'Average: {sum(filtered_counts)/len(filtered_counts):.1f} per chunk\n'
stats_text += f'15-min chunks: {len(minutes)}'
if truncated_bars:
    stats_text += f'\n\n⚠️ Bars >20 truncated\n({len(truncated_bars)} chunks, max: {max_truncated})'
ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, 
        fontsize=11, verticalalignment='top', fontweight='bold',
        bbox=dict(boxstyle='round,pad=0.5', facecolor='wheat', alpha=0.9, edgecolor='black', linewidth=1.5))

# Add legend for day separation
if yesterday_minutes and today_minutes:
    legend_elements = [
        mpatches.Patch(facecolor='blue', alpha=0.1, label=f'Yesterday ({yesterday})'),
        mpatches.Patch(facecolor='green', alpha=0.1, label=f'Today ({today})'),
        mpatches.Patch(facecolor='steelblue', alpha=0.8, label='Normal (≤20 articles)'),
        mpatches.Patch(facecolor='crimson', alpha=0.8, label='Truncated (>20 articles)')
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=10, framealpha=0.9)

# Tight layout to prevent label cutoff
plt.tight_layout()

# Save the chart
output_dir = './data_exports'
os.makedirs(output_dir, exist_ok=True)
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
output_file = os.path.join(output_dir, f'articles_per_minute_fetched_at_{timestamp}.png')
plt.savefig(output_file, dpi=200, bbox_inches='tight', facecolor='white')
print(f"\n✅ Chart saved to: {output_file}")

# Also show the chart
plt.show()
