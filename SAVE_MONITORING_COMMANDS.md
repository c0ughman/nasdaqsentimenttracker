# Database Save Monitoring Commands

## Critical Issues That Would Reduce Saved Articles

### 1. Check for QUEUE_FULL Errors
```bash
heroku logs --tail | grep "QUEUE_FULL"
```
**What it means:** Save queue is full (500 items), new articles can't be queued for saving  
**Impact:** Articles affect score but DON'T save to database  
**Expected:** Should be ZERO occurrences  
**Action if found:** Database is too slow or save worker crashed

---

### 2. Check for DEADLINE_EXCEEDED Errors
```bash
heroku logs --tail | grep "DEADLINE_EXCEEDED"
```
**What it means:** Article waited > 60 seconds in queue, skipped  
**Impact:** Article already affected score but WON'T save to database  
**Expected:** Should be ZERO or < 0.1% of articles  
**Action if found:** Database performance issue or very high article volume

---

### 3. Verify Save Workers Started
```bash
heroku logs | grep "SAVE WORKER: 🚀 STARTED"
```
**Expected output:**
```
DATABASE SAVE WORKER: 🚀 STARTED
TIINGO DATABASE SAVE WORKER: 🚀 STARTED
```
**What it means:** Both save worker threads initialized successfully  
**Expected:** Exactly 2 lines  
**Action if missing:** Save worker thread failed to start, NO ARTICLES SAVING

---

### 4. Check Save Success Rate
```bash
# Count successful saves
heroku logs --tail | grep "SAVE_SUCCESS" | wc -l

# Count failed saves
heroku logs --tail | grep "SAVE_FAILED_ALL_ATTEMPTS" | wc -l
```
**Expected ratio:** > 99% success rate  
**Action if < 95%:** Investigate data validation or database issues

---

### 5. Monitor Queue Wait Times
```bash
heroku logs --tail | grep "wait_time=" | grep "Processing save job"
```
**Expected output:**
```
SAVEQUEUE: 🔄 Processing save job: hash=a1b2c3d4 ticker=AAPL wait_time=0.05s
SAVEQUEUE: 🔄 Processing save job: hash=e5f6g7h8 ticker=MSFT wait_time=0.12s
```
**Expected wait times:** < 1 second  
**Warning threshold:** > 5 seconds  
**Critical threshold:** > 30 seconds (approaching deadline)

---

### 6. Monitor Queue Size
```bash
heroku logs --tail | grep "QUEUE_LARGE"
```
**What it means:** Queue has > 100 items (warning threshold)  
**Expected:** Should be rare  
**Action if frequent:** Database performance issue, consider optimization

---

### 7. Check Save Worker Health
```bash
heroku logs --tail | grep -E "(SAVE_SUCCESS|SAVE_FAILED|Processing save job)"
```
**What to look for:**
- Regular `Processing save job` messages → Worker is running
- Frequent `SAVE_SUCCESS` messages → Saves completing
- No activity → Worker may have crashed

---

### 8. Compare Articles Processed vs Articles Saved
```bash
# Count articles scored (should equal articles queued for save)
heroku logs --tail | grep "Scored and queued impact" | wc -l

# Count save jobs queued
heroku logs --tail | grep "Queued for save" | wc -l

# Count successful saves
heroku logs --tail | grep "SAVE_SUCCESS" | wc -l
```
**Expected:** All three numbers should be very close  
**Red flag:** If queued saves << scored articles → QUEUE_FULL issue  
**Red flag:** If successful saves << queued saves → Worker not processing

---

## Daily Health Check (Every Morning)

### Quick Command:
```bash
heroku logs --tail -n 1000 | grep -E "(QUEUE_FULL|DEADLINE_EXCEEDED|SAVE WORKER|SAVE_SUCCESS|SAVE_FAILED)" | tail -50
```

### What You Should See:
```
✅ DATABASE SAVE WORKER: 🚀 STARTED (2 instances)
✅ Frequent SAVE_SUCCESS messages
✅ ZERO QUEUE_FULL errors
✅ ZERO DEADLINE_EXCEEDED errors
✅ Very few SAVE_FAILED_ALL_ATTEMPTS (< 1%)
```

---

## Alert Thresholds

| Metric | Good | Warning | Critical |
|--------|------|---------|----------|
| Queue wait time | < 1s | 5-10s | > 30s |
| Queue size | < 50 | 100-300 | 500 (full) |
| Success rate | > 99% | 95-99% | < 95% |
| QUEUE_FULL errors | 0 | 1-5 | > 5 |
| DEADLINE_EXCEEDED | 0 | < 1% | > 1% |
| Save worker alive | Yes | - | No |

---

## Troubleshooting

### Issue: QUEUE_FULL errors appearing
**Root cause:** Save worker can't keep up  
**Immediate check:**
```bash
heroku logs --tail | grep "wait_time="
```
If wait times > 10s → Database is slow  

**Solutions:**
1. Check Railway database performance
2. Reduce retry delays (currently 0.1s → 0.15s → 0.225s)
3. Increase queue size (currently 500)
4. Add second save worker thread

---

### Issue: DEADLINE_EXCEEDED errors
**Root cause:** Extreme database slowness  
**Immediate check:**
```bash
heroku logs --tail | grep "SAVE_ATTEMPT"
```
Look at `remaining_time` - if it's decreasing rapidly, database is slow  

**Solutions:**
1. Urgent: Check database status
2. Increase deadline from 60s to 120s
3. Optimize database queries
4. Add database connection pooling

---

### Issue: No SAVE_SUCCESS logs after market opens
**Root cause:** Save worker thread crashed or never started  
**Immediate check:**
```bash
heroku logs | grep "SAVE WORKER"
```
Should see `STARTED` logs. If not, thread failed.  

**Solutions:**
1. Check for exceptions during initialization
2. Restart container
3. Review thread startup code for errors

---

## Expected Behavior (Normal Day)

### At 9:30 AM EST (Market Open)
```
9:30:05 - SCORING: ✅ Scored and queued impact: AAPL impact=+1.23
9:30:05 - SAVEQUEUE: 📝 Queued for save: AAPL hash=a1b2c3d4
9:30:05 - SAVEQUEUE: 🔄 Processing save job: hash=a1b2c3d4 ticker=AAPL wait_time=0.05s
9:30:05 - SAVEQUEUE: ✅ SAVE_SUCCESS hash=a1b2c3d4 id=12345 ticker=AAPL total_time=0.12s
```

**Rate:** 5-20 articles per minute during market hours  
**Wait time:** < 1 second  
**Success rate:** > 99%  
**Queue size:** < 20 items  

---

## Red Flags to Watch For

🚨 **Critical (Stop Everything):**
- Save worker threads not started
- QUEUE_FULL errors (any occurrence)
- No SAVE_SUCCESS logs after market opens

⚠️ **Warning (Monitor Closely):**
- Wait times > 5 seconds
- Queue size > 100
- Success rate < 99%
- Any DEADLINE_EXCEEDED errors

✅ **Normal:**
- Wait times < 1 second
- Queue size < 50
- Success rate > 99%
- Frequent SAVE_SUCCESS logs

