"""
EODHD WebSocket Data Collector V2 - With Second-by-Second Aggregation
Collects real-time ticks and creates:
  - 1-second OHLCV candles (SecondSnapshot)
  - 100-tick OHLCV candles (TickCandle100)
  
Market hours: Connects at 9:30 AM EST, disconnects at 4:00 PM EST

Run with: python manage.py run_websocket_collector_v2
"""

import os
import json
import time
import signal
import sys
import threading
from datetime import datetime, time as datetime_time
from collections import deque
from django.core.management.base import BaseCommand
from django.utils import timezone
import pytz
from api.models import Ticker, OHLCVTick, SecondSnapshot, TickCandle100
from dotenv import load_dotenv

load_dotenv()

# WebSocket library
try:
    import websocket
except ImportError:
    print("❌ ERROR: websocket-client not installed")
    print("   Install with: pip install websocket-client")
    sys.exit(1)

# Configuration
EODHD_API_KEY = os.environ.get('EODHD_API_KEY', '')
WEBSOCKET_URL = f"wss://ws.eodhistoricaldata.com/ws/us?api_token={EODHD_API_KEY}"

# Market hours (EST)
MARKET_OPEN_TIME = datetime_time(9, 30)  # 9:30 AM
MARKET_CLOSE_TIME = datetime_time(16, 0)  # 4:00 PM
EST_TZ = pytz.timezone('US/Eastern')


class Command(BaseCommand):
    help = 'Collect real-time data and create second-by-second candles'
    
    def __init__(self):
        super().__init__()
        self.ws = None
        self.ticker = None
        self.running = True
        
        # Thread safety
        self.lock = threading.Lock()
        
        # Tick buffers
        self.tick_buffer_1sec = {}  # Dict keyed by second timestamp (int) -> list of ticks
        self.tick_buffer_100tick = deque(maxlen=100)  # For 100-tick candles
        self.tick_counter_100 = 0
        self.candle_100_number = 0
        
        # Statistics
        self.total_ticks = 0
        self.total_1sec_candles = 0
        self.total_100tick_candles = 0
        self.connection_start = None
        self.last_second_timestamp = None
        self.last_processed_second = None  # Track which second we last processed
        
        # Rate limiting backoff
        self.consecutive_429_errors = 0
        self.last_429_error_time = None
        
        # Connection state tracking
        self.connection_established = False  # Track if we ever successfully connected
        self.last_connection_time = None
        
    def add_arguments(self, parser):
        parser.add_argument(
            '--symbol',
            type=str,
            default='QLD',
            help='Symbol to track (default: QLD for NASDAQ-100 2x Leveraged ETF)'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Print detailed logs'
        )
        parser.add_argument(
            '--skip-market-hours',
            action='store_true',
            help='Skip market hours check (for testing)'
        )
        
    def handle(self, *args, **options):
        self.symbol = options.get('symbol', 'QLD')
        self.verbose = options.get('verbose', False)
        self.skip_market_hours = options.get('skip_market_hours', False)
        
        # Validate API key
        if not EODHD_API_KEY:
            self.stdout.write(self.style.ERROR(
                '❌ EODHD_API_KEY not set in .env file'
            ))
            return
        
        # Get or create ticker
        self.ticker, _ = Ticker.objects.get_or_create(
            symbol='QLD',
            defaults={'company_name': 'ProShares Ultra QQQ (2x Leveraged NASDAQ-100 ETF)'}
        )
        
        # Initialize 100-tick candle counter from database (resume from last candle)
        last_candle = TickCandle100.objects.filter(ticker=self.ticker).order_by('-candle_number').first()
        self.candle_100_number = last_candle.candle_number if last_candle else 0
        if last_candle:
            self.stdout.write(self.style.SUCCESS(f'🔢 Resuming 100-tick candles from #{self.candle_100_number + 1}'))
        
        # Initialize Finnhub real-time news (optional - fails gracefully if not configured)
        try:
            from api.management.commands.finnhub_realtime_v2 import initialize as init_finnhub
            if init_finnhub():
                self.stdout.write(self.style.SUCCESS('📰 Finnhub real-time news enabled'))
            else:
                self.stdout.write(self.style.NOTICE('📰 Finnhub disabled (API key not set or module unavailable)'))
        except Exception as e:
            self.stdout.write(self.style.NOTICE(f'📰 Finnhub disabled ({str(e)})'))

        
        # Signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # Display startup info
        self.stdout.write(self.style.SUCCESS(
            '\n' + '='*70 + '\n'
            '🚀 EODHD WebSocket Collector V2 (Second-by-Second Aggregation)\n'
            '='*70
        ))
        self.stdout.write(f'📊 Ticker: QLD (NASDAQ-100 2x Leveraged ETF)')
        self.stdout.write(f'📡 Symbol: {self.symbol}')
        self.stdout.write(f'⏰ Market Hours: 9:30 AM - 4:00 PM EST')
        self.stdout.write(f'💾 Saves: 1-second candles + 100-tick candles')
        self.stdout.write('⌨️  Press Ctrl+C to stop\n')
        
        # Market hours loop
        self.connection_start = time.time()
        
        try:
            while self.running:
                if not self.skip_market_hours:
                    # Check market hours
                    market_open, reason = self.is_market_open()
                    
                    if not market_open:
                        self.stdout.write(self.style.WARNING(
                            f'⏸️  Market Closed: {reason}'
                        ))
                        
                        # Calculate sleep time until next market open
                        sleep_seconds = self.seconds_until_market_open()
                        sleep_minutes = int(sleep_seconds / 60)
                        
                        self.stdout.write(
                            f'💤 Sleeping until next market open '
                            f'({sleep_minutes} minutes)...\n'
                        )
                        time.sleep(min(sleep_seconds, 300))  # Check every 5 min max
                        continue
                
                # Market is open, connect
                self.stdout.write(self.style.SUCCESS('✅ Market Open - Connecting...'))
                try:
                    self.connect_and_run()
                    # Successful connection - reset rate limit counter
                    if self.consecutive_429_errors > 0:
                        self.stdout.write(self.style.SUCCESS(
                            f'✅ Connection successful after {self.consecutive_429_errors} rate limit errors. Counter reset.'
                        ))
                        self.consecutive_429_errors = 0
                        self.last_429_error_time = None
                except KeyboardInterrupt:
                    self.running = False
                    break
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'❌ Error: {e}'))
                    if self.running:
                        # Implement exponential backoff for rate limiting
                        if self.consecutive_429_errors > 0:
                            # Exponential backoff: 2^errors seconds, capped at 300 seconds (5 minutes)
                            backoff_seconds = min(2 ** min(self.consecutive_429_errors, 8), 300)
                            self.stdout.write(self.style.WARNING(
                                f'⏳ Rate limit backoff: Waiting {backoff_seconds} seconds before retry '
                                f'(consecutive 429 errors: {self.consecutive_429_errors})'
                            ))
                            time.sleep(backoff_seconds)
                        else:
                            # Normal error - wait 5 seconds
                            self.stdout.write('🔄 Reconnecting in 5 seconds...')
                            time.sleep(5)
        finally:
            self.cleanup()
    
    def is_market_open(self):
        """Check if market is currently open"""
        now_est = datetime.now(EST_TZ)
        current_time = now_est.time()
        current_day = now_est.weekday()
        
        # Check weekend
        if current_day >= 5:  # Saturday = 5, Sunday = 6
            return False, "Weekend"
        
        # Check time
        if current_time < MARKET_OPEN_TIME:
            return False, "Before market open (9:30 AM EST)"
        
        if current_time >= MARKET_CLOSE_TIME:
            return False, "After market close (4:00 PM EST)"
        
        return True, "Market hours"
    
    def seconds_until_market_open(self):
        """Calculate seconds until next market open"""
        now_est = datetime.now(EST_TZ)
        current_day = now_est.weekday()
        
        # If it's Friday after close or weekend, wait until Monday 9:30 AM
        if current_day == 4 and now_est.time() >= MARKET_CLOSE_TIME:  # Friday after close
            days_to_add = 3  # Wait until Monday
        elif current_day == 5:  # Saturday
            days_to_add = 2
        elif current_day == 6:  # Sunday
            days_to_add = 1
        elif now_est.time() >= MARKET_CLOSE_TIME:  # After close on weekday
            days_to_add = 1
        else:  # Before open on weekday
            days_to_add = 0
        
        # Calculate next market open
        next_open = now_est.replace(
            hour=MARKET_OPEN_TIME.hour,
            minute=MARKET_OPEN_TIME.minute,
            second=0,
            microsecond=0
        )
        
        if days_to_add > 0:
            from datetime import timedelta
            next_open += timedelta(days=days_to_add)
        
        seconds = (next_open - now_est).total_seconds()
        return max(0, seconds)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.stdout.write(self.style.WARNING('\n\n⚠️  Received shutdown signal...'))
        self.running = False
        if self.ws:
            self.ws.close()
    
    def connect_and_run(self):
        """Establish WebSocket connection"""
        self.stdout.write(self.style.WARNING('🔌 Connecting to EODHD WebSocket...'))
        
        # Reset connection state for new attempt
        was_connected_before = self.connection_established
        if was_connected_before:
            self.stdout.write(self.style.WARNING(
                f'   Previous connection was established. Attempting reconnection...'
            ))
        
        # Create WebSocket app
        self.ws = websocket.WebSocketApp(
            WEBSOCKET_URL,
            on_open=lambda ws: self.on_open(ws),
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        
        # Disable SSL verification for macOS compatibility
        import ssl
        try:
            self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})
        except Exception as e:
            self.stdout.write(self.style.ERROR(
                f'❌ run_forever() exception: {e}'
            ))
            # run_forever() will call on_close, so we don't need to reset state here
            raise
    
    def on_open(self, ws):
        """Called when WebSocket connection established"""
        self.connection_established = True
        self.last_connection_time = time.time()
        self.stdout.write(self.style.SUCCESS('✅ WebSocket connected!'))
        
        # Reset rate limit counter on successful connection
        if self.consecutive_429_errors > 0:
            self.stdout.write(self.style.SUCCESS(
                f'✅ Connection successful. Resetting rate limit counter (was: {self.consecutive_429_errors})'
            ))
            self.consecutive_429_errors = 0
            self.last_429_error_time = None
        
        # Subscribe
        subscribe_message = {
            "action": "subscribe",
            "symbols": self.symbol
        }
        ws.send(json.dumps(subscribe_message))
        self.stdout.write(self.style.SUCCESS(f'📡 Subscription request sent for: {self.symbol}'))
        self.stdout.write(self.style.WARNING('⏳ Waiting for server confirmation and data stream...'))
        
        # Start aggregation timer
        self.aggregation_thread = threading.Thread(target=self.aggregation_loop, daemon=True)
        self.aggregation_thread.start()
        self.stdout.write(self.style.SUCCESS('⏱️  Aggregation timer started'))

        # Start news fetch timer
        self.news_thread = threading.Thread(target=self.news_loop, daemon=True)
        self.news_thread.start()
        self.stdout.write(self.style.SUCCESS('📰 News fetch loop started\n'))
    
    def news_loop(self):
        """Run periodically to fetch news (non-blocking)"""
        self.stdout.write(self.style.SUCCESS('📰 News loop started'))
        
        while self.running and self.ws and self.ws.sock and self.ws.sock.connected:
            try:
                from api.management.commands.finnhub_realtime_v2 import query_finnhub_for_news
                
                # This function manages its own rate limiting (50s on, 10s off)
                # and puts articles into a queue for processing
                finnhub_result = query_finnhub_for_news()
                
                if finnhub_result.get('queued_for_scoring', 0) > 0:
                    self.stdout.write(self.style.SUCCESS(
                        f'📰 Queued {finnhub_result["queued_for_scoring"]} {finnhub_result["symbol"]} articles for scoring'
                    ))
                elif finnhub_result.get('error'):
                    if self.verbose:
                        self.stdout.write(self.style.WARNING(f'Finnhub query error: {finnhub_result.get("error")}'))
                        
            except Exception as e:
                if self.verbose:
                    self.stdout.write(self.style.ERROR(f'❌ News loop error: {e}'))
            
            # Sleep 1 second
            time.sleep(1)

    def aggregation_loop(self):
        """Run every second on the dot to create 1-second candles"""
        self.stdout.write(self.style.SUCCESS('🔄 Aggregation loop started'))
        
        # Calculate next second boundary
        now = time.time()
        next_second = int(now) + 1  # Next whole second
        
        loop_count = 0
        
        try:
            while self.running and self.ws and self.ws.sock and self.ws.sock.connected:
                try:
                    loop_count += 1
                    # Sleep until next second boundary
                    now = time.time()
                    sleep_time = next_second - now
                    
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    
                    # Process the buffer based on available data, not just wall clock
                    # This handles cases where data is delayed or backfilling
                    
                    # LOCK ACQUIRE for reading keys
                    with self.lock:
                        buffer_keys = sorted(list(self.tick_buffer_1sec.keys()))
                    
                    if not buffer_keys:
                        # Buffer empty, nothing to process
                        # But we should still advance next_second for the loop sleep
                        next_second = current_second + 1 if 'current_second' in locals() else int(time.time()) + 1
                        continue
                        
                    # Determine what to process
                    current_second = int(time.time())
                    
                    max_key = buffer_keys[-1]
                    
                    # Force processing if we have enough data buffered or time has passed
                    # Logic: 
                    # - Process anything strictly older than the newest data we have (max_key)
                    # - This assumes data arrives roughly in order
                    
                    ready_keys = [k for k in buffer_keys if k < max_key]
                    
                    # Also check the max_key itself against wall clock
                    # If max_key is older than 2 seconds ago, assume no more ticks coming for it
                    if max_key < (current_second - 2):
                        ready_keys.append(max_key)
                        
                    # Remove duplicates and sort
                    ready_keys = sorted(list(set(ready_keys)))
                    
                    # DIAGNOSTIC: Log aggregation timing
                    if loop_count <= 5 or loop_count % 10 == 0:
                        current_dt = datetime.fromtimestamp(current_second, tz=pytz.UTC)
                        
                        self.stdout.write(self.style.WARNING(
                            f'⏱️  AGGREGATION TIMING:\n'
                            f'   System time: {current_dt.strftime("%H:%M:%S")} (ts={current_second})\n'
                            f'   Buffer has {len(buffer_keys)} seconds: {buffer_keys[-10:] if len(buffer_keys) > 10 else buffer_keys}\n'
                            f'   Ready to process: {len(ready_keys)} seconds: {ready_keys}\n'
                            f'   Max key in buffer: {max_key}\n'
                            f'   Last processed: {self.last_processed_second}'
                        ))
                    
                    # Process all ready keys
                    processed_count = 0
                    for sec_to_process in ready_keys:
                        # Only process if we haven't already processed this second
                        if self.last_processed_second is None or sec_to_process > self.last_processed_second:
                            self.aggregate_and_save_1sec_candle(sec_to_process)
                            self.last_processed_second = sec_to_process
                            processed_count += 1
                        
                        # Ensure key is removed from buffer even if we skipped processing
                        # (e.g. if we somehow processed it already but didn't clear it)
                        with self.lock:
                            if sec_to_process in self.tick_buffer_1sec:
                                del self.tick_buffer_1sec[sec_to_process]
                    
                    if processed_count > 0 and (loop_count % 10 == 0 or self.verbose):
                        self.stdout.write(self.style.SUCCESS(f'⚡ Processed {processed_count} seconds in this iteration'))

                    # Update next second boundary
                    next_second = int(time.time()) + 1
                    
                except Exception as loop_error:
                    self.stdout.write(self.style.ERROR(f'❌ Aggregation loop iteration failed: {loop_error}'))
                    import traceback
                    self.stdout.write(self.style.ERROR(traceback.format_exc()))
                    # Sleep slightly to avoid tight loop if error persists
                    time.sleep(1)
                    next_second = int(time.time()) + 1
                    
        except Exception as fatal_error:
            self.stdout.write(self.style.ERROR(f'❌ FATAL AGGREGATION LOOP CRASH: {fatal_error}'))
            import traceback
            self.stdout.write(self.style.ERROR(traceback.format_exc()))
        finally:
            self.stdout.write(self.style.WARNING('🛑 Aggregation loop stopped'))
    
    def on_message(self, ws, message):
        """Process incoming tick data"""
        try:
            data = json.loads(message)
            
            # Handle status/error messages (ALWAYS LOG THESE)
            if 'error' in data:
                self.stdout.write(self.style.ERROR(f'❌ Server error: {data.get("error")}'))
                return
            
            if 'status' in data or 'message' in data:
                # ALWAYS log server status/messages (not just verbose mode)
                self.stdout.write(self.style.SUCCESS(f'📢 Server says: {data}'))
                return
            
            # Extract tick data
            symbol = data.get('s', '')
            price = data.get('p', None)
            volume = data.get('v', 0)
            timestamp_unix = data.get('t', None)
            
            # DIAGNOSTIC: Log raw timestamp data
            if self.total_ticks < 5 or self.total_ticks % 100 == 0:
                current_system_time = time.time()
                self.stdout.write(self.style.NOTICE(
                    f'🔍 DIAGNOSTIC Tick #{self.total_ticks + 1}: '
                    f'Raw data timestamp field: {timestamp_unix}, '
                    f'Current system time: {current_system_time:.3f}, '
                    f'Data: {data}'
                ))
            
            # Try bid/ask if no trade price
            if price is None:
                price = data.get('bp', data.get('ap', None))
            
            # Log if we get unexpected data format
            if not symbol or price is None:
                self.stdout.write(self.style.WARNING(
                    f'⚠️  Received data but missing symbol/price: {data}'
                ))
                return
            
            # Log first tick arrival (important milestone!)
            if self.total_ticks == 0:
                self.stdout.write(self.style.SUCCESS(
                    f'🎉 FIRST TICK RECEIVED! Symbol: {symbol}, Price: ${price}, Volume: {volume}'
                ))
            
            # Convert timestamp
            if timestamp_unix:
                try:
                    if timestamp_unix > 10000000000:
                        timestamp_unix = timestamp_unix / 1000
                    dt = datetime.fromtimestamp(timestamp_unix, tz=pytz.UTC)
                    
                    # DIAGNOSTIC: Log time difference
                    if self.total_ticks < 5 or self.total_ticks % 100 == 0:
                        current_time = timezone.now()
                        time_diff = (current_time - dt).total_seconds()
                        self.stdout.write(self.style.WARNING(
                            f'⏰ TIME DIFF: Tick timestamp: {dt.strftime("%H:%M:%S.%f")}, '
                            f'System time: {current_time.strftime("%H:%M:%S.%f")}, '
                            f'Delay: {time_diff:.3f} seconds'
                        ))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'❌ Timestamp conversion error: {e}'))
                    dt = timezone.now()
            else:
                dt = timezone.now()
                if self.total_ticks < 5:
                    self.stdout.write(self.style.WARNING(
                        f'⚠️  No timestamp field in data, using system time: {dt.strftime("%H:%M:%S.%f")}'
                    ))
            
            # Save raw tick
            tick = OHLCVTick.objects.create(
                ticker=self.ticker,
                timestamp=dt,
                price=price,
                volume=volume,
                source='eodhd_ws'
            )
            
            # Add to buffers
            # Group ticks by their exact second (rounded down)
            tick_second = int(dt.timestamp())  # Get Unix timestamp as integer (second boundary)
            
            # DIAGNOSTIC: Log buffer operations
            if self.total_ticks < 5 or self.total_ticks % 100 == 0:
                # Lock for reading keys for log
                with self.lock:
                    keys_log = sorted(list(self.tick_buffer_1sec.keys())[-5:]) if self.tick_buffer_1sec else []
                
                self.stdout.write(self.style.NOTICE(
                    f'📦 BUFFER: Adding tick to second {tick_second} ({dt.strftime("%H:%M:%S")}), '
                    f'Current buffer keys: {keys_log}'
                ))
            
            # LOCK ACQUIRE for writing
            with self.lock:
                if tick_second not in self.tick_buffer_1sec:
                    self.tick_buffer_1sec[tick_second] = []
                    self.stdout.write(self.style.SUCCESS(
                        f'🆕 Created new buffer slot for second {tick_second} ({dt.strftime("%H:%M:%S")})'
                    ))
                self.tick_buffer_1sec[tick_second].append(tick)
            
            # DEBUG: Log first tick added to each second
            # Note: We can't safely check len() without lock, but for debug logging we can risk a slightly stale read
            # or just move it inside lock if critical. Moving inside lock for correctness.
            if self.verbose:
                 with self.lock:
                     is_first = len(self.tick_buffer_1sec[tick_second]) == 1
                 if is_first:
                    self.stdout.write(f'🆕 First tick added to second {tick_second} ({dt.strftime("%H:%M:%S")})')
            
            self.tick_buffer_100tick.append(tick)
            self.tick_counter_100 += 1
            self.total_ticks += 1
            
            # Check if 100-tick candle completed
            if self.tick_counter_100 >= 100:
                self.create_100tick_candle()
                self.tick_counter_100 = 0
            
            # Log progress
            if self.verbose or self.total_ticks % 10 == 0:
                self.stdout.write(
                    f'💾 Tick #{self.total_ticks:>6}: {dt.strftime("%H:%M:%S")} | '
                    f'${price:>8.2f} | Vol: {volume:>8,}'
                )
        
        except json.JSONDecodeError:
            # Always log non-JSON messages (could be important server info)
            self.stdout.write(self.style.WARNING(f'⚠️  Non-JSON message: {message[:200]}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error processing message: {e}'))
            if self.verbose:
                import traceback
                self.stdout.write(self.style.ERROR(traceback.format_exc()))
    
    def aggregate_and_save_1sec_candle(self, second_timestamp):
        """
        Aggregate ticks from a specific second and save as 1-second candle.
        
        Args:
            second_timestamp: Unix timestamp (integer) for the second to process
        """
        # Get ticks for this specific second and remove from buffer
        # LOCK ACQUIRE for popping
        with self.lock:
            ticks = self.tick_buffer_1sec.pop(second_timestamp, [])
        
        # Create timestamp from the second boundary (not from tick timestamps)
        try:
            timestamp = datetime.fromtimestamp(second_timestamp, tz=pytz.UTC)
        except Exception as e:
             self.stdout.write(self.style.ERROR(f'❌ Error converting timestamp {second_timestamp}: {e}'))
             return
        
        # DIAGNOSTIC: Always log what we're trying to process
        if True: # Always log for now to debug
             self.stdout.write(self.style.NOTICE(
                f'🔧 SecondSnapshot ATTEMPT: Processing second {second_timestamp} ({timestamp.strftime("%H:%M:%S")}), '
                f'Found {len(ticks)} ticks in buffer'
            ))
        
        # Check if candle already exists for this second (avoid duplicates)
        # NOTE: This check might be slow if DB is under load. Consider caching latest timestamp.
        existing = SecondSnapshot.objects.filter(
            ticker=self.ticker,
            timestamp=timestamp
        ).first()
        
        if existing:
            # Already created, skip
            self.stdout.write(self.style.WARNING(f'⚠️  SecondSnapshot SKIPPED: {timestamp.strftime("%H:%M:%S")} already exists'))
            return
        
        try:
            if not ticks:
                # No ticks for this second - we still want to create a candle if it's during market hours
                # using the CLOSE of the previous candle (forward fill)
                # BUT for now, let's just return to match previous logic.
                self.stdout.write(self.style.WARNING(
                    f'⚠️  SecondSnapshot SKIPPED: No ticks for second {timestamp.strftime("%H:%M:%S")} (ts={second_timestamp})'
                ))
                return
            
            # Calculate OHLCV from ticks
            open_price = float(ticks[0].price)
            high_price = max(float(t.price) for t in ticks)
            low_price = min(float(t.price) for t in ticks)
            close_price = float(ticks[-1].price)
            total_volume = sum(t.volume for t in ticks)
            tick_count = len(ticks)
            
            # ============================================================
            # REAL-TIME SENTIMENT SCORING V2 (calculate BEFORE creating snapshot)
            # ============================================================
            sentiment_scores = {
                'composite': None,
                'news': None,
                'technical': None
            }
            
            try:
                from api.management.commands.sentiment_realtime_v2 import update_realtime_sentiment
                
                # NOTE: News fetching (query_finnhub_for_news) is now handled in a separate thread (news_loop)
                # It populates a queue that update_realtime_sentiment pulls from automatically.
                # We no longer call query_finnhub_for_news() here to avoid blocking the aggregation loop.
                
                # Get last 60 seconds of snapshots for micro momentum
                # OPTIMIZATION: Limit query to fields we need
                recent_snapshots = list(SecondSnapshot.objects.filter(
                    ticker=self.ticker
                ).order_by('-timestamp')[:60])
                
                # Force macro recalc every minute (when second = 0)
                force_macro = (timestamp.second == 0)
                
                # Calculate sentiment components
                sentiment_result = update_realtime_sentiment(
                    recent_snapshots,
                    ticker_symbol=self.symbol,
                    force_macro_recalc=force_macro
                )
                
                # Store scores for snapshot creation
                sentiment_scores['composite'] = sentiment_result['composite']
                sentiment_scores['news'] = sentiment_result['news']
                sentiment_scores['technical'] = sentiment_result['technical']
                
                # Log sentiment every 10 candles
                if self.verbose or self.total_1sec_candles % 10 == 0:
                    self.stdout.write(self.style.SUCCESS(
                        f'💚 Sentiment #{self.total_1sec_candles}: '
                        f'Composite={sentiment_result["composite"]:+.1f} '
                        f'[News={sentiment_result["news"]:+.1f}, '
                        f'Tech={sentiment_result["technical"]:+.1f}, '
                        f'Micro={sentiment_result["micro_momentum"]:+.1f}] '
                        f'(source: {sentiment_result["source"]})'
                    ))
            
            except Exception as sentiment_error:
                # Don't fail the whole candle if sentiment calculation fails
                # Snapshot will be created with NULL sentiment scores
                self.stdout.write(self.style.WARNING(
                    f'⚠️  Sentiment calculation failed: {sentiment_error}'
                ))
                if self.verbose:
                    import traceback
                    self.stdout.write(traceback.format_exc())
            
            # ============================================================
            
            # Save to SecondSnapshot with exact second boundary timestamp
            # Sentiment scores are included if calculated successfully, otherwise NULL
            try:
                snapshot = SecondSnapshot.objects.create(
                    ticker=self.ticker,
                    timestamp=timestamp,  # Exact second boundary (e.g., 10:30:00.000)
                    ohlc_1sec_open=open_price,
                    ohlc_1sec_high=high_price,
                    ohlc_1sec_low=low_price,
                    ohlc_1sec_close=close_price,
                    ohlc_1sec_volume=total_volume,
                    ohlc_1sec_tick_count=tick_count,
                    composite_score=sentiment_scores['composite'],
                    news_score_cached=sentiment_scores['news'],
                    technical_score_cached=sentiment_scores['technical'],
                    source='eodhd_ws'
                )
                
                self.total_1sec_candles += 1
                self.last_second_timestamp = timestamp
                
                # ALWAYS LOG successful creation
                self.stdout.write(self.style.SUCCESS(
                    f'✅ SecondSnapshot CREATED #{self.total_1sec_candles}: '
                    f'{timestamp.strftime("%H:%M:%S")} | '
                    f'O:{open_price:.2f} H:{high_price:.2f} L:{low_price:.2f} C:{close_price:.2f} | '
                    f'{tick_count} ticks'
                ))
                
            except Exception as create_error:
                self.stdout.write(self.style.ERROR(
                    f'❌ SecondSnapshot CREATION FAILED: {create_error}\n'
                    f'   Timestamp: {timestamp}\n'
                    f'   Data: O={open_price}, H={high_price}, L={low_price}, C={close_price}, V={total_volume}'
                ))
                import traceback
                self.stdout.write(self.style.ERROR(traceback.format_exc()))
                # Re-raise to be caught by outer loop if needed, or just continue
                raise create_error
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ SecondSnapshot PROCESS ERROR: {e}'))
            import traceback
            self.stdout.write(self.style.ERROR(traceback.format_exc()))
    
    def create_100tick_candle(self):
        """Create 100-tick candle from buffer"""
        if len(self.tick_buffer_100tick) < 100:
            return
        
        try:
            # Get last 100 ticks
            ticks = list(self.tick_buffer_100tick)[-100:]
            
            # Calculate OHLCV
            open_price = float(ticks[0].price)
            high_price = max(float(t.price) for t in ticks)
            low_price = min(float(t.price) for t in ticks)
            close_price = float(ticks[-1].price)
            total_volume = sum(t.volume for t in ticks)
            
            first_tick_time = ticks[0].timestamp
            last_tick_time = ticks[-1].timestamp
            duration = (last_tick_time - first_tick_time).total_seconds()
            
            # Increment candle number
            self.candle_100_number += 1
            
            # Save to TickCandle100
            candle = TickCandle100.objects.create(
                ticker=self.ticker,
                candle_number=self.candle_100_number,
                completed_at=last_tick_time,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                total_volume=total_volume,
                first_tick_time=first_tick_time,
                last_tick_time=last_tick_time,
                duration_seconds=duration,
                source='eodhd_ws'
            )
            
            self.total_100tick_candles += 1
            
            self.stdout.write(self.style.SUCCESS(
                f'🎯 100-tick candle #{self.candle_100_number}: '
                f'{last_tick_time.strftime("%H:%M:%S")} | '
                f'O:{open_price:.2f} H:{high_price:.2f} L:{low_price:.2f} C:{close_price:.2f} | '
                f'{duration:.1f}s duration'
            ))
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error creating 100-tick candle: {e}'))
    
    def on_error(self, ws, error):
        """Handle WebSocket errors"""
        error_str = str(error)
        
        self.stdout.write(self.style.ERROR(
            '\n' + '='*70 + '\n'
            '❌ WEBSOCKET ERROR EVENT\n'
            '='*70 + '\n'
            f'Error Details: {error}\n'
        ))
        
        # Detect 429 rate limiting errors
        if '429' in error_str or 'Too Many Requests' in error_str:
            self.consecutive_429_errors += 1
            self.last_429_error_time = time.time()
            
            if self.connection_established:
                self.stdout.write(self.style.WARNING(
                    f'🚫 Error Type: RATE LIMIT (429) - Server closed ESTABLISHED connection\n'
                    f'   Reason: Too many requests detected by server\n'
                    f'   Consecutive 429 errors: {self.consecutive_429_errors}\n'
                    f'   Connection was active before this error'
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f'🚫 Error Type: RATE LIMIT (429) - Connection HANDSHAKE REJECTED\n'
                    f'   Reason: Server rejected connection attempt due to rate limiting\n'
                    f'   Consecutive 429 errors: {self.consecutive_429_errors}\n'
                    f'   Connection never established'
                ))
        
        # Log other common disconnection causes
        elif '502' in error_str or 'Bad Gateway' in error_str:
            self.stdout.write(self.style.WARNING(
                f'🚫 Error Type: SERVER ERROR (502 Bad Gateway)\n'
                f'   Reason: Server is overloaded or undergoing maintenance\n'
                f'   Connection state: {"ESTABLISHED" if self.connection_established else "NOT ESTABLISHED"}'
            ))
        elif 'timeout' in error_str.lower():
            self.stdout.write(self.style.WARNING(
                f'🚫 Error Type: CONNECTION TIMEOUT\n'
                f'   Reason: Network or server did not respond in time\n'
                f'   Connection state: {"ESTABLISHED" if self.connection_established else "NOT ESTABLISHED"}'
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f'🚫 Error Type: UNKNOWN\n'
                f'   Connection state: {"ESTABLISHED" if self.connection_established else "NOT ESTABLISHED"}'
            ))
        
        self.stdout.write(self.style.ERROR('='*70 + '\n'))
    
    def on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close"""
        # Determine if this was an established connection or failed handshake
        was_connected = self.connection_established
        connection_duration = None
        if self.last_connection_time:
            connection_duration = time.time() - self.last_connection_time
        
        self.stdout.write(self.style.WARNING(
            '\n' + '='*70 + '\n'
            '🔌 WEBSOCKET DISCONNECTION EVENT\n'
            '='*70
        ))
        
        if was_connected:
            self.stdout.write(self.style.WARNING(
                f'📊 Connection Status: ESTABLISHED connection was CLOSED\n'
                f'⏱️  Connection Duration: {connection_duration:.1f} seconds\n'
                f'📈 Total ticks collected: {self.total_ticks:,}\n'
                f'📊 SecondSnapshots created: {self.total_1sec_candles:,}'
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f'📊 Connection Status: HANDSHAKE FAILED (connection never established)\n'
                f'❌ Could not complete WebSocket handshake with server'
            ))
        
        if close_status_code:
            self.stdout.write(self.style.WARNING(
                f'🔢 Close Code: {close_status_code}'
            ))
            if close_msg:
                self.stdout.write(self.style.WARNING(
                    f'💬 Close Message: {close_msg}'
                ))
        else:
            self.stdout.write(self.style.WARNING(
                f'🔢 Close Code: None (abnormal closure)'
            ))
        
        if self.consecutive_429_errors > 0:
            self.stdout.write(self.style.WARNING(
                f'⚠️  Rate Limit Context: {self.consecutive_429_errors} consecutive 429 errors'
            ))
        
        self.stdout.write(self.style.WARNING('='*70 + '\n'))
        
        # Reset connection state
        self.connection_established = False
    
    def cleanup(self):
        """Cleanup and display statistics"""
        # Process any remaining ticks for all seconds in buffer
        # LOCK ACQUIRE for key listing
        with self.lock:
            keys = sorted(self.tick_buffer_1sec.keys())
            
        if keys:
            for second_timestamp in keys:
                self.aggregate_and_save_1sec_candle(second_timestamp)
        
        if self.ws:
            self.ws.close()
        
        # Calculate statistics
        uptime = time.time() - self.connection_start if self.connection_start else 0
        uptime_str = f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m {int(uptime % 60)}s"
        
        self.stdout.write(self.style.SUCCESS(
            f'\n' + '='*70 + '\n'
            f'📊 Session Statistics\n'
            f'='*70 + '\n'
            f'   Total ticks collected: {self.total_ticks:,}\n'
            f'   1-second candles created: {self.total_1sec_candles:,}\n'
            f'   100-tick candles created: {self.total_100tick_candles:,}\n'
            f'   Uptime: {uptime_str}\n'
            f'   Last candle: {self.last_second_timestamp.strftime("%Y-%m-%d %H:%M:%S") if self.last_second_timestamp else "N/A"}\n'
            f'='*70
        ))
        self.stdout.write(self.style.SUCCESS('✅ Collector stopped cleanly'))
