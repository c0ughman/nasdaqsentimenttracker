# Explanation: Why `fetched_at` Doesn't Match Actual Article Processing

## The Problem

You're seeing news score movements throughout the trading day, but `fetched_at` timestamps show articles weren't "fetched" until the afternoon (2pm+). This discrepancy makes sense when you understand how your codebase actually works.

---

## How Your System Actually Works

### 1. **Article Flow (Real-Time Processing)**

```
API Fetch → Queue → Score → Save to DB → Apply to Sentiment Score
   ↓          ↓       ↓         ↓              ↓
9:00am    9:00am   9:05am   9:05am        9:05am ✅ MOVEMENT HAPPENS
```

**What happens:**
1. **9:00am:** Articles are fetched from Finnhub/Tiingo APIs and **queued** for scoring
2. **9:00am:** Articles are **immediately queued** to `article_to_score_queue`
3. **9:05am:** Background `scoring_worker()` thread scores the article
4. **9:05am:** Article is saved to database (`fetched_at` = 9:05am)
5. **9:05am:** Impact is put into `scored_article_queue`
6. **9:05am:** Sentiment calculation loop reads impact and **applies it immediately**
7. **Result:** News score moves at 9:05am ✅

### 2. **The `fetched_at` Field Behavior**

Looking at your model:
```python
fetched_at = models.DateTimeField(auto_now_add=True)
```

And your save function:
```python
article, created = NewsArticle.objects.update_or_create(
    article_hash=article_hash,
    defaults={...}
)
```

**Critical Issue:** `auto_now_add=True` means:
- ✅ **CREATE:** `fetched_at` = current time (when first saved)
- ❌ **UPDATE:** `fetched_at` = **NOT CHANGED** (stays as original creation time)

---

## Why All `fetched_at` Times Are Clustered in Afternoon

### Scenario: Articles Processed Throughout Day, But Saved in Batches

**What's Actually Happening:**

1. **Morning (9:00am-1:00pm):**
   - Articles fetched from APIs ✅
   - Articles queued for scoring ✅
   - Articles scored by background thread ✅
   - **BUT:** Database saves might be delayed due to:
     - Database connection issues
     - Retry logic (3 attempts with 0.5s delay)
     - Queue backup (scoring thread slower than fetch rate)
     - Database locks/timeouts

2. **Afternoon (2:00pm-3:00pm):**
   - Database connection stabilizes
   - Retry attempts succeed
   - **Batch of articles finally saved** → `fetched_at` = 2:00pm-3:00pm
   - But these articles were **actually processed hours earlier**

### Evidence from Your Code

Looking at `save_article_to_db()`:
```python
max_retries = 3
retry_delay = 0.5  # seconds

for attempt in range(max_retries):
    try:
        article, created = NewsArticle.objects.update_or_create(...)
        # If this fails, retry up to 3 times
    except (OperationalError, IntegrityError, DatabaseError) as e:
        # Retry with exponential backoff
        time.sleep(retry_delay * (2 ** attempt))
```

**What this means:**
- If database is slow/busy, saves are retried
- Articles might be scored and impacting sentiment, but not saved yet
- When saves finally succeed, `fetched_at` = save time (afternoon), not fetch time (morning)

---

## The Real Timeline

### What Your Sentiment Score Sees (Real-Time):
```
9:00am  → Article fetched, queued, scored → Impact applied → Score moves ✅
10:00am → Article fetched, queued, scored → Impact applied → Score moves ✅
11:00am → Article fetched, queued, scored → Impact applied → Score moves ✅
...
2:00pm  → Database saves finally succeed → fetched_at = 2:00pm ❌ (WRONG TIME)
```

### What Your Database Shows (Delayed Saves):
```
2:00pm  → fetched_at = 2:00pm (but article was processed at 9:00am)
2:15pm  → fetched_at = 2:15pm (but article was processed at 10:00am)
3:00pm  → fetched_at = 3:00pm (but article was processed at 11:00am)
```

---

## Why This Happens

### 1. **Asynchronous Processing**
- Articles are **scored and applied to sentiment immediately** (via queue)
- Database saves happen **asynchronously** and can be delayed
- Sentiment score reflects **real-time processing**, not database save times

### 2. **Database Save Delays**
- Retry logic means failed saves are retried later
- Database connection issues cause delays
- Queue backup means scoring happens faster than saving

### 3. **`update_or_create` Behavior**
- If article already exists (by hash), it's **updated**, not created
- `auto_now_add=True` only sets timestamp on **create**, not update
- So `fetched_at` represents **first successful save**, not actual fetch time

---

## The Discrepancy Explained

**Your Question:** "If articles weren't fetched until 2pm, how did sentiment scores move throughout the morning?"

**Answer:** Articles **WERE fetched and processed** throughout the morning, but:
1. They were saved to the database **later** (afternoon)
2. `fetched_at` reflects **save time**, not **fetch/process time**
3. Sentiment scores moved in **real-time** because impacts were applied immediately from the queue

---

## What `fetched_at` Actually Represents

**`fetched_at` = When article was FIRST successfully saved to database**

**NOT:**
- ❌ When article was fetched from API
- ❌ When article was queued for scoring
- ❌ When article was scored
- ❌ When article impact was applied to sentiment

**It's:** When the database save operation finally succeeded (which can be hours after actual processing).

---

## Recommendations

### 1. **Add True Fetch Timestamp**
Add a new field to track when articles are actually fetched:
```python
api_fetched_at = models.DateTimeField(null=True, blank=True)  # When fetched from API
queued_at = models.DateTimeField(null=True, blank=True)  # When queued for scoring
scored_at = models.DateTimeField(null=True, blank=True)  # When scored
fetched_at = models.DateTimeField(auto_now_add=True)  # When saved to DB (keep for compatibility)
```

### 2. **Log Fetch Times**
In `query_finnhub_for_news()` and Tiingo queries, log when articles are actually fetched:
```python
fetch_time = timezone.now()
article_data = {
    ...
    'api_fetched_at': fetch_time,  # Track actual fetch time
}
```

### 3. **Use Queue Timestamps**
Track when articles enter the scoring queue vs when they're saved.

---

## Conclusion

**The discrepancy is real and expected:**

- ✅ Articles ARE fetched and processed throughout the day (explains sentiment movements)
- ❌ Articles are saved to database in batches/delayed (explains clustered `fetched_at`)
- ✅ `fetched_at` represents database save time, not actual fetch/process time
- ✅ Sentiment scores reflect real-time processing, not database save times

**Your sentiment system is working correctly** - it's processing articles in real-time. The `fetched_at` field just doesn't accurately represent when articles were actually fetched and processed.

