"""
Market hours utility for checking if trading is active.

Handles:
- US Central Time trading hours (8:30 AM - 4:00 PM CT)
- Weekend trading (starts Sunday evening when NZ markets open)
- Major US stock market holidays
"""

from datetime import datetime, time, timedelta
import pytz


# Central Time zone
CENTRAL_TZ = pytz.timezone('America/Chicago')

# Trading hours in Central Time
MARKET_OPEN_TIME = time(8, 30)  # 8:30 AM CT
MARKET_CLOSE_TIME = time(15, 0)  # 3:00 PM CT (4:00 PM ET - actual market close)

# Major US stock market holidays (format: (month, day))
# These are the main ones - New Year's Day, MLK Day, Presidents Day, Good Friday,
# Memorial Day, Independence Day, Labor Day, Thanksgiving, Christmas
MARKET_HOLIDAYS_2025 = [
    (1, 1),    # New Year's Day
    (1, 20),   # Martin Luther King Jr. Day
    (2, 17),   # Presidents Day
    (4, 18),   # Good Friday
    (5, 26),   # Memorial Day
    (7, 4),    # Independence Day
    (9, 1),    # Labor Day
    (11, 27),  # Thanksgiving
    (12, 25),  # Christmas
]

MARKET_HOLIDAYS_2026 = [
    (1, 1),    # New Year's Day
    (1, 19),   # Martin Luther King Jr. Day
    (2, 16),   # Presidents Day
    (4, 3),    # Good Friday
    (5, 25),   # Memorial Day
    (7, 3),    # Independence Day (observed)
    (9, 7),    # Labor Day
    (11, 26),  # Thanksgiving
    (12, 25),  # Christmas
]


def is_market_holiday(dt):
    """Check if the given date is a US stock market holiday."""
    date_tuple = (dt.month, dt.day)

    if dt.year == 2025:
        return date_tuple in MARKET_HOLIDAYS_2025
    elif dt.year == 2026:
        return date_tuple in MARKET_HOLIDAYS_2026

    # For other years, just check common fixed holidays
    return date_tuple in [(1, 1), (7, 4), (12, 25)]


def is_market_open():
    """
    Check if the market is currently open for trading.

    Returns:
        tuple: (is_open: bool, reason: str)
    """
    # Get current time in Central Time
    now_ct = datetime.now(CENTRAL_TZ)

    # Check if it's a holiday
    if is_market_holiday(now_ct):
        return False, f"Market holiday ({now_ct.strftime('%B %d, %Y')})"

    # Get current day of week (0=Monday, 6=Sunday)
    weekday = now_ct.weekday()
    current_time = now_ct.time()

    # Sunday evening (market opens when NZ markets open - around 5 PM CT Sunday)
    if weekday == 6:  # Sunday
        # Market opens at 5:00 PM CT on Sunday for week start
        if current_time >= time(17, 0):
            return True, "Trading active (Sunday evening session)"
        else:
            return False, "Market closed (weekend)"

    # Saturday - always closed
    elif weekday == 5:  # Saturday
        return False, "Market closed (weekend)"

    # Monday-Friday - check trading hours
    else:
        if MARKET_OPEN_TIME <= current_time <= MARKET_CLOSE_TIME:
            return True, "Trading active (regular hours)"
        else:
            return False, f"Market closed (outside trading hours: 8:30 AM - 4:00 PM CT)"


def get_market_status():
    """
    Get detailed market status information.

    Returns:
        dict: {
            'is_open': bool,
            'reason': str,
            'current_time_ct': str,
            'next_open': str (optional)
        }
    """
    is_open, reason = is_market_open()
    now_ct = datetime.now(CENTRAL_TZ)

    status = {
        'is_open': is_open,
        'reason': reason,
        'current_time_ct': now_ct.strftime('%Y-%m-%d %I:%M:%S %p %Z'),
    }

    return status


def get_current_trading_day():
    """
    Get the current trading day date (in UTC).
    
    Returns the current date if it's a trading day (Mon-Fri, not holiday),
    otherwise returns the most recent trading day (typically Friday).
    
    Returns:
        datetime.date: The current or most recent trading day
    """
    # Start with today in Central Time (market timezone)
    now_ct = datetime.now(CENTRAL_TZ)
    current_date = now_ct.date()
    
    # Walk backwards up to 7 days to find most recent trading day
    for days_back in range(8):  # Check today + previous 7 days
        check_date = current_date - timedelta(days=days_back)
        check_datetime = datetime.combine(check_date, time(12, 0))  # Noon
        check_datetime = CENTRAL_TZ.localize(check_datetime)
        
        # Get day of week (0=Monday, 6=Sunday)
        weekday = check_datetime.weekday()
        
        # Check if it's a weekday (not Saturday=5 or Sunday=6)
        if weekday >= 5:  # Weekend
            continue
            
        # Check if it's a holiday
        if is_market_holiday(check_datetime):
            continue
        
        # Found a trading day
        return check_date
    
    # Fallback: if we somehow didn't find a trading day in the past week,
    # return today (shouldn't happen in practice)
    return current_date
