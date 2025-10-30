# Complete Commit History - Nasdaq Sentiment Tracker

This document contains the complete commit history from the GitHub repository `nasdaqsentimenttracker`.

---

## Commit #1 (Most Recent)
**Hash:** `db36aa9085696d7d41d404ac79b263975454c404`  
**Author:** c0ughman <58052516+c0ughman@users.noreply.github.com>  
**Date:** 2025-10-28 12:40:12 -0500  
**Subject:** Update start.sh

**Description:**
(No additional description)

---

## Commit #2
**Hash:** `6fb3b3446eb3b38b64547781bbe43970c1e01ded`  
**Author:** c0ughman <58052516+c0ughman@users.noreply.github.com>  
**Date:** 2025-10-28 12:30:26 -0500  
**Subject:** Update start.sh

**Description:**
(No additional description)

---

## Commit #3
**Hash:** `eb1166cc1830998cc22c727d3ee50e92225a44a8`  
**Author:** c0ughman <58052516+c0ughman@users.noreply.github.com>  
**Date:** 2025-10-28 12:27:06 -0500  
**Subject:** Update start.sh

**Description:**
(No additional description)

---

## Commit #4
**Hash:** `cf896eea18280969d0903c87eddd90a9f0c84ba2`  
**Author:** c0ughman <58052516+c0ughman@users.noreply.github.com>  
**Date:** 2025-10-24 10:40:32 -0500  
**Subject:** Fix time label to show actual timestamp and move up 50px

**Description:**
- Fixed interpolateValue to use timeLabel property from data points
- Added fallback to format timestamp if timeLabel is missing
- Moved label up 50 pixels (bottom: -32px -> bottom: 18px)
- Now displays actual timestamp from hovered data point
- No more 'undefined' - shows formatted time (HH:MM:SS)

---

## Commit #5
**Hash:** `7d5eec464592dad38ddaee7cf8e144c068f7e722`  
**Author:** c0ughman <58052516+c0ughman@users.noreply.github.com>  
**Date:** 2025-10-24 10:37:19 -0500  
**Subject:** Completely remake time label element from scratch

**Description:**
- Simplified CSS with basic properties (no complex transforms/flex)
- Uses class toggle (.show) instead of direct display manipulation
- Text wrapped in <strong> tag for extra emphasis
- Simple positioning with left offset calculation
- Monospace font family for clear time display
- Bold font weight for better visibility
- Clean padding and border radius
- Z-index 9999 to ensure it's on top

---

## Commit #6
**Hash:** `5263816e3492e79b60a13167060c80af05cbafb3`  
**Author:** c0ughman <58052516+c0ughman@users.noreply.github.com>  
**Date:** 2025-10-24 10:35:54 -0500  
**Subject:** Fix time label text visibility - make text clearly visible

**Description:**
- Changed text color to pure black (#000000) for maximum contrast
- Increased font size to 14px and font-weight to 800 (extra bold)
- Set line-height to 34px (same as box height) for perfect vertical centering
- Removed padding to prevent text cutoff
- Added explicit monospace font family for clear time display
- Added overflow:visible to ensure text isn't hidden
- Increased box size slightly (90x34px)

---

## Commit #7
**Hash:** `004e2991dd63263719fb54425e3bd4f0a372af71`  
**Author:** c0ughman <58052516+c0ughman@users.noreply.github.com>  
**Date:** 2025-10-24 10:33:33 -0500  
**Subject:** Fix time label visibility and make it square

**Description:**
- Changed bottom position from 24px to -28px to show below x-axis
- Made it square-shaped (85x32px with proper aspect ratio)
- Increased z-index to 1000 to ensure it's above all other elements
- Changed display to flex for proper text centering
- Larger font (13px) with better letter spacing
- Stronger shadow for better visibility

---

## Commit #8
**Hash:** `5ae1603a73f5c64eb4d372ae4c7a149680276cfb`  
**Author:** c0ughman <58052516+c0ughman@users.noreply.github.com>  
**Date:** 2025-10-24 10:32:13 -0500  
**Subject:** Fix time label size - make it larger and more visible

**Description:**
- Increased font size from 10px to 12px
- Larger padding (6px 12px instead of 4px 8px)
- Added min-width of 80px to ensure visibility
- Centered text alignment
- Bolder font weight and better shadow

---

## Commit #9
**Hash:** `4e7fe1a60f07ef2a765f644f694b28787f125897`  
**Author:** c0ughman <58052516+c0ughman@users.noreply.github.com>  
**Date:** 2025-10-24 10:30:34 -0500  
**Subject:** Update historical sentiment chart with time-based timeframes and hover time label

**Description:**
- Changed timeframe buttons from point-based to time-based (5 min, 15 min, 30 min, 1 hr, 2 hrs, 4 hrs, 8 hrs)
- Updated timeframeConfig to filter data by actual time ranges (5-480 minutes)
- Added orange time label box that appears at bottom of hover line on chart
- Each timeframe now shows data from that specific time period dynamically

---

## Commit #10
**Hash:** `403c3c6ef7524eefe4bf5783a5a79b20a136c3dd`  
**Author:** c0ughman <58052516+c0ughman@users.noreply.github.com>  
**Date:** 2025-10-24 09:28:33 -0500  
**Subject:** Make Market Breadth section transparent

**Description:**
(No additional description)

---

## Commit #11
**Hash:** `2a0685f3b2acfc437990528c585f14b77ab835e3`  
**Author:** c0ughman <58052516+c0ughman@users.noreply.github.com>  
**Date:** 2025-10-23 17:33:14 -0500  
**Subject:** CRITICAL: Fix .env file overriding Railway environment variables

**Description:**

Problem:
- .env file contains USE_SQLITE=True for local development
- load_dotenv() was overriding Railway's environment variables
- Railway tried to use SQLite instead of PostgreSQL

Solution:
- Changed load_dotenv(override=False)
- Railway environment variables now take precedence
- .env only used as fallback for missing variables

This fixes the PostgreSQL database connection on Railway.

---

## Commit #12
**Hash:** `eb836c4d9abd7043e7461db291ac757f9f4cbd18`  
**Author:** c0ughman <58052516+c0ughman@users.noreply.github.com>  
**Date:** 2025-10-23 17:19:21 -0500  
**Subject:** Fix Railway PostgreSQL database configuration

**Description:**

CRITICAL FIX: Django was using SQLite instead of PostgreSQL on Railway

Problem:
- dj_database_url.config() was not parsing DATABASE_URL correctly
- Railway environment had DATABASE_URL set but Django used SQLite
- All data saved locally, Railway database empty
- Admin login failed, API returned 404

Solution:
- Use dj_database_url.parse() instead of config()
- Explicitly check for DATABASE_URL environment variable
- Force PostgreSQL when DATABASE_URL is present

Changes:
- backend/config/settings.py: Fixed database configuration logic
- backend/api/management/commands/run_nasdaq_sentiment.py: Added SKIP_MARKET_HOURS_CHECK
- Added diagnostic scripts for testing

Testing:
- Run: python diagnose_railway_db.py
- Should now show PostgreSQL engine, not SQLite

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>

---

## Commit #13
**Hash:** `819d298e628c567be5d37b04fee3d29d9ffda3f0`  
**Author:** c0ughman <58052516+c0ughman@users.noreply.github.com>  
**Date:** 2025-10-23 16:12:58 -0500  
**Subject:** Configure for production deployment on Railway and Netlify

**Description:**

Changes:
- Update frontend API URL to point to Railway production backend
- Configure Netlify to serve from frontend/ directory
- Add comprehensive deployment documentation
- Update database with latest sentiment analysis

Frontend:
- Changed API_BASE_URL from ngrok to Railway production URL
- URL: https://nasdaqsentimenttracker-production.up.railway.app/api

Netlify:
- Set publish directory to "frontend" in netlify.toml
- Ensures Netlify serves frontend/nasdaq.html correctly

Documentation:
- Created RAILWAY_ENV_VARIABLES.md with all required env vars
- Created DEPLOYMENT_CHECKLIST.md with step-by-step guide
- Includes troubleshooting and verification steps

Ready for production deployment to Railway and Netlify

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>

---

## Commit #14
**Hash:** `de2ce3e54ad742d641e08751ab61f24ec1c6ffc0`  
**Author:** c0ughman <58052516+c0ughman@users.noreply.github.com>  
**Date:** 2025-10-23 15:50:32 -0500  
**Subject:** Organize project as monorepo with backend and frontend

**Description:**
- Merged backend code from c0ughman/nasdaqsentimenttracker
- Merged frontend code from c0ughman/nasdaqst-frontend
- Preserved existing .env configuration and database
- Added all documentation and utility scripts
- Project now organized with clear backend/ and frontend/ directories

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>

---

## Commit #15
**Hash:** `a1531f22e4edfafc7e6640f76e50d1be7e354730`  
**Author:** c0ughman <58052516+c0ughman@users.noreply.github.com>  
**Date:** 2025-10-23 12:23:34 -0500  
**Subject:** Update nasdaq.html

**Description:**
(No additional description)

---

## Commit #16
**Hash:** `77fc7fa17459f9162399a53648e232ae396e74d2`  
**Author:** c0ughman <58052516+c0ughman@users.noreply.github.com>  
**Date:** 2025-10-22 20:55:05 -0500  
**Subject:** Adding railway url

**Description:**
(No additional description)

---

## Commit #17 (Oldest)
**Hash:** `23a724736bd4a650cd22ef61a9d709896b5242d2`  
**Author:** c0ughman <58052516+c0ughman@users.noreply.github.com>  
**Date:** 2025-10-22 20:42:47 -0500  
**Subject:** Add files via upload

**Description:**
(No additional description)

---

## Summary

**Total Commits:** 17  
**Repository:** nasdaqsentimenttracker  
**Branch:** main  
**Current HEAD:** db36aa9085696d7d41d404ac79b263975454c404

### Timeline Overview

- **October 22, 2025:** Initial commit and setup
- **October 23, 2025:** Major deployment and configuration work
  - Monorepo organization
  - Production deployment configuration
  - Railway PostgreSQL fixes
  - Environment variable fixes
- **October 24, 2025:** Frontend UI improvements
  - Historical chart timeframes
  - Time label improvements
- **October 28, 2025:** Backend startup script updates

### Key Changes

1. **Production Deployment (Oct 23):** 
   - Configured Railway and Netlify deployment
   - Fixed database configuration issues
   - Added comprehensive documentation

2. **Frontend Enhancements (Oct 24):**
   - Improved time label visibility on charts
   - Added time-based timeframes to historical sentiment chart

3. **Backend Maintenance (Oct 28):**
   - Updated start.sh script multiple times for Railway deployment

---

*Generated from repository: https://github.com/c0ughman/nasdaqsentimenttracker*

