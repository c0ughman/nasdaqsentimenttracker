# Detailed Commit History with File Changes

This document shows each commit with the files that were changed.

---

## db36aa9 - Update start.sh (2025-10-28)
**Files Changed:**
- backend/start.sh (modified)

---

## 6fb3b34 - Update start.sh (2025-10-28)
**Files Changed:**
- backend/start.sh (modified)

---

## eb1166c - Update start.sh (2025-10-28)
**Files Changed:**
- backend/start.sh (modified)

---

## cf896ee - Fix time label to show actual timestamp and move up 50px (2025-10-24)
**Files Changed:**
- frontend/nasdaq.html (modified)

**Changes:**
- Fixed interpolateValue to use timeLabel property from data points
- Added fallback to format timestamp if timeLabel is missing
- Moved label up 50 pixels (bottom: -32px -> bottom: 18px)
- Now displays actual timestamp from hovered data point

---

## 7d5eec4 - Completely remake time label element from scratch (2025-10-24)
**Files Changed:**
- frontend/nasdaq.html (modified)

**Changes:**
- Simplified CSS with basic properties
- Uses class toggle (.show) instead of direct display manipulation
- Text wrapped in <strong> tag for extra emphasis
- Simple positioning with left offset calculation

---

## 5263816 - Fix time label text visibility (2025-10-24)
**Files Changed:**
- frontend/nasdaq.html (modified)

**Changes:**
- Changed text color to pure black (#000000)
- Increased font size to 14px and font-weight to 800
- Set line-height to 34px for perfect vertical centering

---

## 004e299 - Fix time label visibility and make it square (2025-10-24)
**Files Changed:**
- frontend/nasdaq.html (modified)

**Changes:**
- Changed bottom position from 24px to -28px
- Made it square-shaped (85x32px)
- Increased z-index to 1000

---

## 5ae1603 - Fix time label size (2025-10-24)
**Files Changed:**
- frontend/nasdaq.html (modified)

**Changes:**
- Increased font size from 10px to 12px
- Larger padding (6px 12px instead of 4px 8px)
- Added min-width of 80px

---

## 4e7fe1a - Update historical sentiment chart with time-based timeframes (2025-10-24)
**Files Changed:**
- frontend/nasdaq.html (modified)

**Changes:**
- Changed timeframe buttons from point-based to time-based
- Updated timeframeConfig to filter data by actual time ranges
- Added orange time label box that appears at bottom of hover line

---

## 403c3c6 - Make Market Breadth section transparent (2025-10-24)
**Files Changed:**
- frontend/nasdaq.html (modified)

---

## 2a0685f - CRITICAL: Fix .env file overriding Railway environment variables (2025-10-23)
**Files Changed:**
- backend/config/settings.py (modified)

**Changes:**
- Changed load_dotenv(override=False)
- Railway environment variables now take precedence
- .env only used as fallback for missing variables

---

## eb836c4 - Fix Railway PostgreSQL database configuration (2025-10-23)
**Files Changed:**
- backend/api/management/commands/run_nasdaq_sentiment.py (modified)
- backend/config/settings.py (modified)
- backend/diagnose_railway_db.py (new file)
- backend/test_db_connection.py (new file)

**Changes:**
- Use dj_database_url.parse() instead of config()
- Explicitly check for DATABASE_URL environment variable
- Force PostgreSQL when DATABASE_URL is present
- Added SKIP_MARKET_HOURS_CHECK
- Added diagnostic scripts for testing (diagnose_railway_db.py, test_db_connection.py)

---

## 819d298 - Configure for production deployment on Railway and Netlify (2025-10-23)
**Files Changed:**
- DEPLOYMENT_CHECKLIST.md (new file)
- PRODUCTION_TESTING_GUIDE.md (new file)
- RAILWAY_ENV_VARIABLES.md (new file)
- backend/db.sqlite3 (modified)
- frontend/nasdaq.html (modified)
- netlify.toml (modified)

**Changes:**
- Changed API_BASE_URL from ngrok to Railway production URL
- URL: https://nasdaqsentimenttracker-production.up.railway.app/api
- Set publish directory to "frontend" in netlify.toml
- Created comprehensive deployment documentation
- Updated database with latest sentiment analysis

---

## de2ce3e - Organize project as monorepo with backend and frontend (2025-10-23)
**Files Changed:**
- Added .gitignore
- Added multiple documentation files (BATCH_PROCESSING_GUIDE.md, COMPOSITE_SCORE_EXPLAINED.md, etc.)
- Added backend/ directory with all Django code
- Added frontend/ directory with nasdaq.html
- Added root-level files (setup scripts, test files)
- Modified nasdaq.html (moved to frontend/)

**Changes:**
- Merged backend code from c0ughman/nasdaqsentimenttracker
- Merged frontend code from c0ughman/nasdaqst-frontend
- Preserved existing .env configuration and database
- Added all documentation and utility scripts
- Project now organized with clear backend/ and frontend/ directories

---

## a1531f2 - Update nasdaq.html (2025-10-23)
**Files Changed:**
- nasdaq.html (modified)

---

## 77fc7fa - Adding railway url (2025-10-22)
**Files Changed:**
- nasdaq.html (modified)

**Changes:**
- Added Railway URL configuration

---

## 23a7247 - Add files via upload (2025-10-22)
**Files Changed:**
- nasdaq.html (new file)
- netlify.toml (new file)

**Changes:**
- Initial commit with basic frontend files

---

*For full commit details, see COMMIT_HISTORY.md*

