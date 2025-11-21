# WebSocket Collector V2 - Quick Start Guide

## Starting the Collector

### Production Mode (Market Hours Only)
```bash
python3 manage.py run_websocket_collector_v2
```

### Testing Mode (Anytime, with verbose logging)
```bash
python3 manage.py run_websocket_collector_v2 --skip-market-hours --verbose
```

### Background Mode (Recommended for Production)
```bash
nohup python3 manage.py run_websocket_collector_v2 > collector.log 2>&1 &
```

To check the logs:
```bash
tail -f collector.log
```

## What to Look For (Healthy System)

### On Startup:
```
🚀 EODHD WebSocket Collector V2 (PRODUCTION-READY)
✅ WebSocket connected!
⏱️  Aggregation timer started
💚 Async sentiment calculator started
💓 Connection health monitor started
🎉 FIRST TICK RECEIVED!
```

### During Operation:
```
✅ SecondSnapshot #123: 10:30:15 | O:45.23 H:45.25 L:45.22 C:45.24 | 12 ticks
💚 Sentiment: Composite=+12.3 [News=+5.2, Tech=+8.1]
💓 Health: Connection active, last data 3s ago, 1234 ticks, 123 candles
```

## Warning Signs (What to Watch For)

### ⚠️ Normal Warnings (Not Critical):
- `⚠️  SecondSnapshot SKIPPED: No ticks for second...` - Normal during low volume
- `⚠️  Sentiment calculation error` - Sentiment will retry next second
- `⚠️  LATE TICK: Second already processed` - Tick arrived too late, skipped

### ❌ Critical Errors (Action Needed):
- `❌ STALE CONNECTION DETECTED` - Connection will auto-reconnect
- `❌ SecondSnapshot CREATION FAILED after 3 attempts` - Check database connection
- `❌ FATAL AGGREGATION LOOP CRASH` - Should NOT happen - restart if you see this

## Stopping the Collector

### If Running in Foreground:
Press `Ctrl+C` once. You'll see:
```
⚠️  Received shutdown signal...
🧹 Starting cleanup...
⏳ Processing remaining seconds in buffer...
✅ Collector stopped cleanly
```

### If Running in Background:
```bash
# Find the process
ps aux | grep run_websocket_collector_v2

# Kill it gracefully
kill <PID>
```

## Health Checks

### Check if Running:
```bash
ps aux | grep run_websocket_collector_v2
```

### Check Latest Data:
```bash
python3 manage.py shell -c "
from api.models import SecondSnapshot, Ticker
ticker = Ticker.objects.get(symbol='QLD')
latest = SecondSnapshot.objects.filter(ticker=ticker).order_by('-timestamp').first()
print(f'Latest: {latest.timestamp} - Close: ${latest.ohlc_1sec_close}')
"
```

### Check Database Connection:
```bash
python3 manage.py shell -c "
from django.db import connection
connection.ensure_connection()
print('Database: Connected ✅')
"
```

## Troubleshooting

### Problem: No snapshots being created
**Check:**
1. Is market open? (9:30 AM - 4:00 PM EST, weekdays)
2. Are ticks being received? (look for tick count increasing)
3. Is database connected? (run health check above)

**Solution:**
```bash
# Test with skip market hours flag
python3 manage.py run_websocket_collector_v2 --skip-market-hours --verbose
```

### Problem: System stops after 30 minutes
**This should NOT happen anymore!** The new reliability fixes prevent this.

If it still happens:
1. Check `collector.log` for errors
2. Check database connection
3. Check memory usage: `ps aux | grep run_websocket_collector_v2`
4. Report the issue with logs

### Problem: High memory usage
**Normal:** 100-200 MB is expected
**High:** >500 MB - check for errors in logs

**Solution:**
```bash
# Restart the collector
kill <PID>
python3 manage.py run_websocket_collector_v2
```

### Problem: Database "locked" errors
**This should NOT happen anymore!** Ticks are no longer written to database.

If you still see it:
- Check PostgreSQL connection
- Check for other processes writing to database
- Restart database connection pool

## Performance Metrics

### Expected Values:
- **Ticks/second:** 10-100 (varies by market activity)
- **Candles/minute:** 60 (one per second)
- **Buffer size:** 1-5 seconds (should be small)
- **Memory usage:** 100-200 MB
- **CPU usage:** 5-15%

### Concerning Values:
- **Buffer size >20 seconds:** Aggregation falling behind
- **No ticks for >120 seconds:** Connection stale (will auto-reconnect)
- **Memory >500 MB:** Memory leak (restart)

## Advanced Options

### Custom Symbol (Not Recommended):
```bash
python3 manage.py run_websocket_collector_v2 --symbol AAPL
```
Note: System is designed for QLD. Other symbols may not work correctly.

### Extra Verbose Logging:
```bash
python3 manage.py run_websocket_collector_v2 --verbose
```
Shows detailed tick-by-tick processing.

## Integration with Other Scripts

The collector integrates with:
- `sentiment_realtime_v2.py` - Async sentiment calculation
- `finnhub_realtime_v2.py` - Real-time news (currently disabled)
- `run_nasdaq_sentiment.py` - Minute-level analysis

**All three can run simultaneously without conflicts!**

## Monitoring Checklist

Run these checks daily:

- [ ] Check process is running: `ps aux | grep run_websocket_collector_v2`
- [ ] Check latest snapshot: `tail -1 collector.log | grep "SecondSnapshot"`
- [ ] Check for errors: `grep "❌" collector.log | tail -10`
- [ ] Check memory: `ps aux | grep run_websocket_collector_v2`
- [ ] Verify data in database: Check latest SecondSnapshot timestamp

## Support

If you encounter issues not covered here:
1. Check `collector.log` for detailed errors
2. Run health checks above
3. Try restarting the collector
4. Check database and network connectivity

## Summary

✅ **Start:** `python3 manage.py run_websocket_collector_v2`
✅ **Monitor:** `tail -f collector.log`
✅ **Stop:** `Ctrl+C` or `kill <PID>`
✅ **Health:** Look for ✅, 💚, and 💓 in logs
✅ **Troubleshoot:** Check this guide + `collector.log`
