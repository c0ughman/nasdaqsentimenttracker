# Complete Code Flow: Why Database Saves Are Delayed

## The Complete Flow

### STEP 1: Articles Are Fetched (Every Second)
**File:** `finnhub_realtime_v2.py` lines 737-883

```python
def query_finnhub_for_news():
    # Called every second by WebSocket collector
    # ...
    articles = client.company_news(symbol, _from=yesterday, to=today)
    
    # Process new articles (top 3 only)
    for article in articles[:3]:
        article_data = {
            'headline': article.get('headline', ''),
            'summary': article.get('summary', ''),
            'symbol': symbol,
            'url': url,
            'published': article.get('datetime', 0)
        }
        
        # ⚡ IMMEDIATELY QUEUED - NO DELAY HERE
        article_to_score_queue.put_nowait(article_data)
        queued += 1
        logger.info(f"Queued {symbol} article for scoring...")
```

**What happens:**
- ✅ Articles fetched from API
- ✅ **IMMEDIATELY** queued to `article_to_score_queue`
- ✅ Returns immediately (non-blocking)
- ✅ **No delay at this stage**

---

### STEP 2: Background Thread Scores Articles
**File:** `finnhub_realtime_v2.py` lines 664-706

```python
def scoring_worker():
    """Background thread that scores articles from queue."""
    while _scoring_thread_running:
        # Get article from queue (block for up to 1 second)
        article_data = article_to_score_queue.get(timeout=1.0)
        
        # ⚡ SCORE IMMEDIATELY
        impact = score_article_with_ai(
            article_data['headline'],
            article_data['summary'],
            article_data['symbol']
        )
        
        # ⚡ PUT IMPACT IN QUEUE IMMEDIATELY (BEFORE SAVE!)
        scored_article_queue.put(impact)
        
        # ⚠️ SAVE TO DATABASE (CAN FAIL/DELAY)
        try:
            save_article_to_db(article_data, impact)
        except Exception as e:
            logger.error(f"Error saving article to database: {e}")
            # ⚠️ CONTINUE EVEN IF SAVE FAILS!
            # Impact already applied to sentiment!
```

**What happens:**
- ✅ Article scored immediately
- ✅ **Impact put in queue BEFORE database save**
- ⚠️ Database save happens AFTER impact is queued
- ⚠️ **If save fails, impact still applied to sentiment!**

---

### STEP 3: Sentiment Score Updated (Real-Time)
**File:** `sentiment_realtime_v2.py` lines 419-433

```python
# Check for newly scored articles (from Finnhub thread)
impacts = get_scored_articles()  # Gets from scored_article_queue
if impacts:
    total_impact = sum(impacts)
    for article_impact in impacts:
        news_updated += article_impact  # ⚡ APPLIED IMMEDIATELY
        logger.info(f"Applied Finnhub article impact: {article_impact:+.2f}")
```

**What happens:**
- ✅ Impacts read from queue **immediately**
- ✅ Applied to sentiment score **in real-time**
- ✅ **Happens BEFORE database save completes**
- ✅ **Sentiment moves even if save fails!**

---

### STEP 4: Database Save (WITH RETRY LOGIC - THIS IS WHERE DELAYS HAPPEN)
**File:** `finnhub_realtime_v2.py` lines 270-550

```python
def save_article_to_db(article_data, impact):
    max_retries = 3
    retry_delay = 0.5  # seconds
    
    for attempt in range(max_retries):
        try:
            # ... validation code ...
            
            # ⚠️ DATABASE SAVE ATTEMPT
            article, created = NewsArticle.objects.update_or_create(
                article_hash=article_hash,
                defaults={...}
            )
            
            # ✅ SUCCESS - fetched_at set to NOW
            if created:
                logger.info(f"NEWSSAVING: ✅ SAVED_NEW...")
            return article
            
        except IntegrityError as e:
            # ⚠️ RETRY ON CONSTRAINT VIOLATION
            logger.warning(f"NEWSSAVING: 🔄 DUPLICATE attempt={attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)  # ⚠️ DELAY: 0.5s, 1s, 2s
                retry_delay *= 2
                continue  # ⚠️ RETRY LATER
            
        except OperationalError as e:
            # ⚠️ RETRY ON DATABASE ERROR (connection, deadlock, timeout)
            logger.warning(f"NEWSSAVING: 🔄 {error_type} attempt={attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)  # ⚠️ DELAY: 0.5s, 1s, 2s
                retry_delay *= 2
                continue  # ⚠️ RETRY LATER
            
        except DatabaseError as e:
            # ⚠️ RETRY ON ANY DATABASE ERROR
            logger.warning(f"NEWSSAVING: 🔄 DATABASE_ERROR attempt={attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)  # ⚠️ DELAY: 0.5s, 1s, 2s
                retry_delay *= 2
                continue  # ⚠️ RETRY LATER
    
    # ❌ ALL RETRIES FAILED - RETURN NONE
    logger.error(f"NEWSSAVING: ❌ FAILED after {max_retries} attempts")
    return None
```

**What happens:**
- ⚠️ **First attempt fails** (database busy/connection issue)
- ⚠️ **Wait 0.5 seconds**, retry
- ⚠️ **Second attempt fails** (still busy)
- ⚠️ **Wait 1 second**, retry
- ⚠️ **Third attempt fails** (still busy)
- ⚠️ **Wait 2 seconds**, retry
- ✅ **Fourth attempt succeeds** → `fetched_at` = NOW (could be hours later!)

---

### STEP 5: The `fetched_at` Field Behavior
**File:** `api/models.py` line 261

```python
class NewsArticle(models.Model):
    fetched_at = models.DateTimeField(auto_now_add=True)
```

**What `auto_now_add=True` means:**
- ✅ **CREATE:** `fetched_at` = current time (when first saved successfully)
- ❌ **UPDATE:** `fetched_at` = **NOT CHANGED** (stays as original creation time)

**What `update_or_create()` does:**
```python
article, created = NewsArticle.objects.update_or_create(
    article_hash=article_hash,
    defaults={...}
)
```

- If article **doesn't exist** → **CREATE** → `fetched_at` = NOW ✅
- If article **already exists** → **UPDATE** → `fetched_at` = **UNCHANGED** ❌

---

## The Complete Timeline Example

### What Actually Happens:

```
9:00:00 AM EST - Article fetched from API
9:00:00 AM EST - Article queued for scoring ✅
9:00:05 AM EST - Article scored ✅
9:00:05 AM EST - Impact put in scored_article_queue ✅
9:00:05 AM EST - Sentiment score updated ✅ MOVEMENT HAPPENS!
9:00:05 AM EST - Try to save to database...
9:00:05 AM EST - ❌ Database save FAILS (connection timeout)
9:00:05 AM EST - Wait 0.5 seconds...
9:00:06 AM EST - Retry save...
9:00:06 AM EST - ❌ Database save FAILS (deadlock)
9:00:06 AM EST - Wait 1 second...
9:00:07 AM EST - Retry save...
9:00:07 AM EST - ❌ Database save FAILS (still busy)
9:00:07 AM EST - Wait 2 seconds...
9:00:09 AM EST - Retry save...
9:00:09 AM EST - ❌ Database save FAILS (connection issue)
9:00:09 AM EST - Return None (all retries exhausted)

... hours pass, database connection stabilizes ...

2:00:00 PM EST - Article somehow gets saved (maybe retry from another thread?)
2:00:00 PM EST - ✅ SAVE SUCCEEDS → fetched_at = 2:00 PM EST
```

**Result:**
- ✅ Sentiment score moved at **9:00:05 AM**
- ❌ `fetched_at` shows **2:00:00 PM**
- ❌ **5-hour discrepancy!**

---

## Why Saves Cluster in Afternoon

### Scenario: Database Connection Issues

**Morning (9:00 AM - 1:00 PM):**
- Articles fetched ✅
- Articles scored ✅
- Impacts applied ✅
- **Database saves FAIL** (connection issues, timeouts, deadlocks)
- Retries exhausted, saves abandoned

**Afternoon (2:00 PM - 3:00 PM):**
- Database connection stabilizes
- Some retry mechanism succeeds
- **Batch of articles finally saved**
- `fetched_at` = 2:00 PM - 3:00 PM (but articles processed hours earlier)

---

## The Critical Code Sections

### 1. Impact Applied BEFORE Save (Line 696)
```python
# Put result in scored queue
scored_article_queue.put(impact)  # ⚡ HAPPENS FIRST

# Save article to database
save_article_to_db(article_data, impact)  # ⚠️ HAPPENS AFTER
```

### 2. Save Can Fail Silently (Line 692)
```python
try:
    save_article_to_db(article_data, impact)
except Exception as e:
    logger.error(f"Error saving article to database: {e}")
    # Continue even if save fails - don't break sentiment calculation
    # ⚠️ IMPACT ALREADY APPLIED!
```

### 3. Retry Logic Causes Delays (Lines 488-550)
```python
except OperationalError as e:
    if attempt < max_retries - 1:
        time.sleep(retry_delay)  # ⚠️ DELAYS HERE
        retry_delay *= 2  # Exponential backoff
        continue  # Retry later
```

### 4. `fetched_at` Only Set on Create (Model line 261)
```python
fetched_at = models.DateTimeField(auto_now_add=True)
# Only set when article is FIRST created
# NOT updated on subsequent updates
```

---

## Why This Design Exists

### The Intent:
1. **Don't block sentiment calculation** - sentiment updates happen immediately
2. **Resilient to database issues** - retries prevent data loss
3. **Non-blocking** - scoring thread doesn't wait for database

### The Problem:
1. **`fetched_at` doesn't reflect actual fetch time** - it reflects save time
2. **Delayed saves create misleading timestamps** - clustered in afternoon
3. **No tracking of actual fetch time** - only save time is recorded

---

## What Needs to Change

### Current Flow:
```
Fetch → Queue → Score → Queue Impact → Apply Impact → Try Save → Retry → Save
  ✅      ✅      ✅         ✅            ✅           ⚠️        ⚠️      ✅
```

### Problem:
- `fetched_at` = Save time (can be hours after fetch)
- No record of actual fetch time
- Sentiment moves before save completes

### Solution Options:

1. **Track actual fetch time separately:**
   ```python
   api_fetched_at = models.DateTimeField()  # When fetched from API
   queued_at = models.DateTimeField()  # When queued
   scored_at = models.DateTimeField()  # When scored
   fetched_at = models.DateTimeField(auto_now_add=True)  # When saved (keep for compatibility)
   ```

2. **Save fetch time when queuing:**
   ```python
   article_data = {
       ...
       'api_fetched_at': timezone.now(),  # Track actual fetch time
   }
   ```

3. **Make saves synchronous (but slower):**
   - Wait for save to complete before queuing impact
   - Blocks sentiment calculation
   - Not recommended (defeats purpose of async design)

---

## Summary

**The delay happens because:**

1. ✅ Articles are fetched and processed **immediately** (explains sentiment movements)
2. ⚠️ Database saves have **retry logic** (3 attempts with exponential backoff)
3. ⚠️ Saves can **fail and retry later** (hours later)
4. ⚠️ `fetched_at` reflects **save time**, not fetch time
5. ⚠️ When saves finally succeed, `fetched_at` = current time (afternoon)
6. ✅ But articles were **actually processed hours earlier** (morning)

**The code is working as designed** - it prioritizes real-time sentiment updates over database persistence. The `fetched_at` field just doesn't accurately represent when articles were actually fetched and processed.

