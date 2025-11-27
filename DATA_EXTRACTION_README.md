# Data Extraction & Analysis Guide

This guide shows you how to extract today's data from Railway and create charts/analysis.

## 📋 Prerequisites

1. **Add Railway Database URL to .env**

```bash
# Add this to your .env file:
RAILWAY_DATABASE_URL=postgresql://postgres:xxxxx@xxx.railway.app:5432/railway
```

Get this URL from your Railway dashboard → Database → Connect.

2. **Install Python dependencies**

```bash
pip install pandas matplotlib seaborn psycopg2-binary
```

---

## 🚀 Quick Start (3 Steps)

### Step 1: Extract Data from Railway

```bash
# Extract today's data from Railway
python manage.py extract_todays_data --database=railway

# Extract specific date
python manage.py extract_todays_data --database=railway --date=2025-11-25

# Export only JSON (default is both CSV and JSON)
python manage.py extract_todays_data --database=railway --format=json

# Custom output directory
python manage.py extract_todays_data --database=railway --output-dir=./my_data
```

**Output:** Creates CSV and JSON files in `./data_exports/`

---

### Step 2: Analyze & Create Charts

```bash
python analyze_data.py
```

**Output:**
- Charts in `./analysis_output/` folder
- Statistics printed to console

---

### Step 3: View Results

Check the `analysis_output/` folder for:

📊 **Generated Charts:**
- `second_snapshots_sentiment_*.png` - Second-by-second sentiment timeline
- `ohlc_QLD_*.png` - OHLC price chart with sentiment overlay
- `volume_heatmap_*.png` - Trading volume heatmap by hour
- `analysis_runs_sentiment_*.png` - Analysis run sentiment timeline
- `price_vs_sentiment_*.png` - Stock price vs sentiment scatter plot
- `sentiment_distribution_*.png` - Histogram of sentiment scores

---

## 📊 What Data Gets Extracted

### SecondSnapshot Data
- Second-by-second OHLC candles (open, high, low, close, volume)
- Composite sentiment scores
- Cached news/technical scores
- Tick counts

### AnalysisRun Data
- Composite sentiment scores
- Sentiment labels (BULLISH, NEUTRAL, BEARISH)
- Component scores (base sentiment, surprise, novelty, etc.)
- Stock price data (OHLC, volume, price change %)
- Technical indicators (RSI, MACD, etc.)
- Reddit sentiment
- Analyst recommendations
- Article counts (total, cached, new)

---

## 🛠️ Advanced Usage

### Extract from Local Database

```bash
python manage.py extract_todays_data --database=local
```

### Date Range Analysis

Extract multiple days:

```bash
# Extract last 7 days
for i in {0..6}; do
    date=$(date -v-${i}d +%Y-%m-%d)
    python manage.py extract_todays_data --database=railway --date=$date
done
```

### Custom Analysis Script

Load and analyze the exported data in Python:

```python
import pandas as pd

# Load data
snapshots = pd.read_csv('./data_exports/second_snapshots_20251126_*.csv')
analysis = pd.read_csv('./data_exports/analysis_runs_20251126_*.csv')

# Convert timestamp to datetime
snapshots['timestamp'] = pd.to_datetime(snapshots['timestamp'])
analysis['timestamp'] = pd.to_datetime(analysis['timestamp'])

# Your custom analysis here
print(snapshots.describe())
print(analysis.groupby('ticker_symbol')['composite_score'].mean())
```

---

## 📈 Example Statistics Output

```
📊 DATA ANALYSIS SUMMARY
======================================================================

📈 SECOND-BY-SECOND DATA (SecondSnapshots):
  Total records: 23,400
  Tickers: QLD
  Time range: 2025-11-26 09:30:00 to 2025-11-26 16:00:00

  Price Statistics:
    QLD:
      Open: $85.23
      Close: $86.45
      High: $87.12
      Low: $84.98
      Total Volume: 1,234,567

  Sentiment Statistics:
    Records with sentiment: 1,200
    Score range: -12.50 to 48.30
    Average score: 23.45

📰 ANALYSIS RUNS:
  Total records: 78
  Tickers: QLD
  Time range: 2025-11-26 09:30:00 to 2025-11-26 16:00:00

  Sentiment Statistics:
    Score range: -8.20 to 52.10
    Average score: 28.45
    Median score: 26.30
    Std deviation: 12.45

  Sentiment Label Distribution:
    BULLISH            45
    NEUTRAL            28
    BEARISH             5

  Articles Analyzed:
    Total: 1,567
    Average per run: 20.1
    New articles: 234
    Cached articles: 1,333
```

---

## 🐛 Troubleshooting

### Issue: "RAILWAY_DATABASE_URL not found"
**Solution:** Add your Railway database URL to `.env`:
```bash
RAILWAY_DATABASE_URL=postgresql://postgres:xxxxx@xxx.railway.app:5432/railway
```

### Issue: "No data files found"
**Solution:** Run the extraction command first:
```bash
python manage.py extract_todays_data --database=railway
```

### Issue: "Module not found: pandas"
**Solution:** Install required packages:
```bash
pip install pandas matplotlib seaborn psycopg2-binary
```

### Issue: Connection timeout to Railway
**Solution:** Check your Railway database is running and URL is correct. Try:
```bash
# Test connection
python -c "import psycopg2; from urllib.parse import urlparse; import os; url = urlparse(os.getenv('RAILWAY_DATABASE_URL')); print('Connecting...'); conn = psycopg2.connect(database=url.path[1:], user=url.username, password=url.password, host=url.hostname, port=url.port); print('✓ Connected!')"
```

---

## 📁 File Structure

```
backend/
├── data_exports/                    # Extracted data (CSV/JSON)
│   ├── second_snapshots_20251126_*.csv
│   ├── second_snapshots_20251126_*.json
│   ├── analysis_runs_20251126_*.csv
│   └── analysis_runs_20251126_*.json
├── analysis_output/                 # Generated charts
│   ├── second_snapshots_sentiment_*.png
│   ├── ohlc_QLD_*.png
│   ├── volume_heatmap_*.png
│   └── ...
├── api/management/commands/
│   └── extract_todays_data.py      # Extraction command
└── analyze_data.py                  # Analysis script
```

---

## 💡 Tips

1. **Schedule Daily Exports:** Add to cron to automatically extract data:
   ```bash
   0 17 * * 1-5 cd /path/to/backend && python manage.py extract_todays_data --database=railway
   ```

2. **Compare Days:** Export multiple days and compare sentiment patterns

3. **Export to Excel:** Use `pandas` to convert CSV to Excel:
   ```python
   import pandas as pd
   df = pd.read_csv('./data_exports/analysis_runs_20251126_*.csv')
   df.to_excel('analysis_data.xlsx', index=False)
   ```

4. **Share Data:** The exported CSV/JSON files are portable - easy to share with others

---

## 🎯 Next Steps

- Modify `analyze_data.py` to create custom charts
- Build correlation analysis between price and sentiment
- Create time-series forecasting models
- Export data to dashboarding tools (Tableau, Power BI, etc.)
