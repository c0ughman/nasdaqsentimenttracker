# Additional Database Save Errors - Comprehensive Analysis

## 🔍 Additional Errors Found (After Initial Fixes)

### 1. **Float Field Validation Errors**
**Error:** `ValueError: could not convert NaN/Infinity to database value`
**Cause:** 
- `base_sentiment`, `article_score`, `weighted_contribution` could be NaN or Infinity
- Math operations can produce NaN (0/0, inf/inf)
- Infinity from division by very small numbers
**Impact:** Database rejects NaN/Inf values
**Fix:** Validate all float fields before saving

### 2. **Null Bytes in Text Fields (PostgreSQL)**
**Error:** `ValueError: A string literal cannot contain NUL (0x00) characters`
**Cause:**
- Article headline/summary/URL contains `\x00` (null byte)
- Common in web scraping from malformed HTML
**Impact:** PostgreSQL rejects strings with null bytes
**Fix:** Strip null bytes from all text fields

### 3. **Invalid Unicode/Control Characters**
**Error:** `UnicodeDecodeError` or database encoding error
**Cause:**
- Invalid UTF-8 sequences in article text
- Control characters (0x00-0x1F) in text
- Emoji or special characters that don't encode properly
**Impact:** Database encoding errors
**Fix:** Clean text to valid UTF-8, remove control characters

### 4. **Database Deadlocks**
**Error:** `OperationalError: deadlock detected`
**Cause:**
- Two transactions trying to update same article simultaneously
- Concurrent `update_or_create()` calls with same hash
**Impact:** Transaction aborted
**Fix:** Retry with backoff (already implemented for OperationalError)

### 5. **Transaction Serialization Failures**
**Error:** `OperationalError: could not serialize access`
**Cause:**
- High concurrency with SERIALIZABLE isolation level
- Concurrent updates to same rows
**Impact:** Transaction rolled back
**Fix:** Retry logic (already implemented)

### 6. **Memory Errors with Large Articles**
**Error:** `MemoryError` or database buffer overflow
**Cause:**
- Extremely long article text (megabytes)
- Database query buffer exhausted
**Impact:** Process crash or database error
**Fix:** Limit text field lengths more aggressively

### 7. **Invalid DateTime Values**
**Error:** `ValueError: year is out of range` or `OverflowError`
**Cause:**
- Timestamp outside database range (year 1-9999)
- Invalid Unix timestamp (negative or too large)
**Impact:** DateTime field validation fails
**Fix:** Validate timestamp is in valid range

### 8. **Database Connection Pool Exhausted**
**Error:** `OperationalError: connection pool exhausted`
**Cause:**
- Too many concurrent save operations
- Connections not released properly
**Impact:** Cannot create new connections
**Fix:** Already handled by retry logic, but need to ensure connection closing

### 9. **Database Disk Full**
**Error:** `OperationalError: database or disk is full`
**Cause:**
- Disk space exhausted
- Database size limit reached
**Impact:** Cannot write to database
**Fix:** Catch and log specifically (cannot fix programmatically)

### 10. **Invalid Article Hash Format**
**Error:** Hash validation error or constraint violation
**Cause:**
- Hash not exactly 32 characters (MD5 should be 32 hex chars)
- Hash contains invalid characters
**Impact:** Constraint violation
**Fix:** Validate hash format before saving

### 11. **Timezone-Naive DateTime (Edge Case)**
**Error:** `ValueError: DateTimeField received a naive datetime`
**Cause:**
- DateTime without timezone info on timezone-aware field
**Impact:** Field validation fails
**Fix:** Already handled but add extra validation

### 12. **Float Overflow in Calculations**
**Error:** `OverflowError: float overflow`
**Cause:**
- Multiplication of very large floats (impact * 100 * 100)
- Exponential calculations
**Impact:** Cannot compute value
**Fix:** Clamp values before calculations

### 13. **Invalid Character in URL Field**
**Error:** `ValidationError: Enter a valid URL`
**Cause:**
- URL contains invalid characters (spaces, newlines)
- URL not properly encoded
**Impact:** URLField validation fails
**Fix:** URL encode and clean before saving

### 14. **Text Field with Only Whitespace**
**Error:** May not be caught, but creates poor data quality
**Cause:**
- Article has headline that's only spaces/tabs/newlines
**Impact:** Empty-looking articles in database
**Fix:** Strip and validate text has actual content

### 15. **Database Lock Timeout**
**Error:** `OperationalError: lock timeout exceeded`
**Cause:**
- Table locked for too long by another process
- Long-running transaction blocking writes
**Impact:** Cannot acquire lock to write
**Fix:** Already handled by retry logic

## 🎯 Priority Errors to Fix

### High Priority:
1. **NaN/Infinity in float fields** - Common with math operations
2. **Null bytes in text** - Common in web scraping
3. **Invalid Unicode** - Common with international content
4. **Text with only whitespace** - Data quality issue

### Medium Priority:
5. **Invalid URLs** - Occasional issue
6. **Float overflow** - Rare but possible
7. **DateTime out of range** - Very rare

### Low Priority (Already Handled):
8. Deadlocks - Retry logic handles
9. Serialization errors - Retry logic handles
10. Connection pool - Retry logic handles

## 📝 What Needs to be Added

### 1. Text Sanitization Function
```python
def sanitize_text(text, max_length=None):
    """Remove null bytes, control chars, clean whitespace"""
    if not text:
        return ""
    
    # Remove null bytes (PostgreSQL issue)
    text = text.replace('\x00', '')
    
    # Remove control characters (0x00-0x1F except whitespace)
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\t\n\r')
    
    # Normalize whitespace
    text = ' '.join(text.split())
    
    # Truncate if needed
    if max_length:
        text = text[:max_length]
    
    return text.strip()
```

### 2. Float Validation Function
```python
def safe_float(value, default=0.0, min_val=-1e10, max_val=1e10):
    """Validate float is not NaN/Inf and within range"""
    import math
    
    if value is None:
        return default
    
    # Check for NaN/Infinity
    if math.isnan(value) or math.isinf(value):
        return default
    
    # Clamp to safe range
    return max(min_val, min(max_val, float(value)))
```

### 3. URL Validation Function
```python
def safe_url(url, max_length=500):
    """Clean and validate URL"""
    if not url:
        return ""
    
    # Remove whitespace
    url = url.strip()
    
    # Remove newlines and control chars
    url = ''.join(char for char in url if ord(char) >= 32)
    
    # Basic URL encoding for spaces
    url = url.replace(' ', '%20')
    
    # Truncate
    return url[:max_length]
```

### 4. DateTime Validation Function
```python
def safe_datetime(dt):
    """Ensure datetime is valid and in range"""
    from django.utils import timezone
    
    if not dt:
        return timezone.now()
    
    # Check year is in reasonable range
    if dt.year < 1900 or dt.year > 2100:
        return timezone.now()
    
    # Ensure timezone-aware
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    
    return dt
```

### 5. Comprehensive NEWSSAVING Logging

Every log message should include "NEWSSAVING" for easy grep:

**Entry point:**
```
NEWSSAVING: Attempting save for {symbol} article: {headline[:50]}...
```

**Success:**
```
NEWSSAVING: ✓ SAVED article_hash={hash} ticker={symbol} created={True/False}
```

**Sanitization:**
```
NEWSSAVING: ⚠️ Sanitized null bytes from headline
NEWSSAVING: ⚠️ Float value was NaN, using default
NEWSSAVING: ⚠️ URL contained invalid chars, cleaned
```

**Retry:**
```
NEWSSAVING: 🔄 RETRY attempt={n} reason={error} ticker={symbol}
```

**Failure:**
```
NEWSSAVING: ❌ FAILED after 3 attempts: {error} ticker={symbol} hash={hash}
```

**Data validation:**
```
NEWSSAVING: 📊 Data validated: headline_len={x} url_len={y} impact={z}
```

## 🔧 Complete Fix Required

Need to add to both `finnhub_realtime_v2.py` and `tiingo_realtime_news.py`:

1. Import math for NaN/Inf checks
2. Add sanitization functions
3. Add NEWSSAVING to ALL log messages
4. Add validation before database save
5. Add specific error handling for new error types
6. Log data characteristics for debugging

