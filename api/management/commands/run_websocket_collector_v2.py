"""
EODHD WebSocket Data Collector V2 - With Second-by-Second Aggregation (PRODUCTION-READY)

Collects real-time ticks and creates:
  - 1-second OHLCV candles (SecondSnapshot) with real-time sentiment
  - 100-tick OHLCV candles (TickCandle100)

RELIABILITY FEATURES:
  - Ticks kept in-memory only (no database writes for performance)
  - Async sentiment calculation (non-blocking)
  - Robust error handling with exponential backoff retry
  - Connection health monitoring with auto-reconnect
  - Thread-safe buffer management
  - Graceful degradation on errors

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
from api.models import Ticker, SecondSnapshot, TickCandle100
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

# Optional: enable/disable Finnhub integration for second-by-second processing
FINNHUB_SECOND_BY_SECOND_ENABLED = os.getenv('FINNHUB_SECOND_BY_SECOND_ENABLED', 'false').lower() in (
    '1',
    'true',
    'yes',
)

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

        # Tick buffers (in-memory only - ticks NOT saved to database)
        # Structure: {second_timestamp: [{'price': float, 'volume': int, 'timestamp': datetime}, ...]}
        self.tick_buffer_1sec = {}  # Dict keyed by second timestamp (int) -> list of tick dicts
        self.tick_buffer_100tick = deque(maxlen=100)  # For 100-tick candles (list of tick dicts)
        self.tick_counter_100 = 0
        self.candle_100_number = 0

        # Sentiment calculation (async queue)
        self.sentiment_queue = deque(maxlen=10)  # Queue of sentiment calculation results
        self.sentiment_thread = None
        self.sentiment_running = False

        # News threads (initialize to None for safety)
        self.news_thread = None
        self.tiingo_thread = None

        # Statistics
        self.total_ticks = 0
        self.total_1sec_candles = 0
        self.total_100tick_candles = 0
        self.connection_start = None
        self.last_second_timestamp = None
        self.last_processed_second = None  # Track which second we last processed

        # Duplicate prevention
        self.processed_seconds = set() # Keep track of seconds we've already closed

        # Rate limiting backoff
        self.consecutive_429_errors = 0
        self.last_429_error_time = None

        # Connection state tracking
        self.connection_established = False  # Track if we ever successfully connected
        self.last_connection_time = None
        self.last_data_received_time = None  # Track when we last received data
        self.was_established_before_close = False  # Track if connection was established before close (for fast reconnect)

        # Health monitoring
        self.last_heartbeat_time = None
        self.heartbeat_thread = None

        # CRITICAL: Track subscribed symbols for reconnection (EODHD requirement)
        self.subscribed_symbols = []  # List of symbols we're subscribed to

        # Error logging deduplication (thread-safe)
        self.error_logged = False
        self.disconnect_logged = False
        self.disconnect_log_lock = threading.Lock()  # Thread-safe lock for disconnect logging
        self.error_log_lock = threading.Lock()  # Thread-safe lock for error logging
        self._last_disconnect_log_time = 0  # Timestamp of last disconnect log
        self._closing_in_progress = False  # Flag to prevent concurrent close handling

        # Connection metrics
        self.total_connections = 0
        self.total_disconnections = 0
        self.connection_start_time = None
        
        # Tick logging (summary only, not individual ticks)
        self.last_tick_log_time = time.time()
        self.ticks_since_last_log = 0
        
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
        
        # Automatic duplicate instance detection and cleanup
        # Works on Railway and local environments
        try:
            import subprocess
            current_pid = os.getpid()
            matching_pids = []
            
            # Try multiple methods to find duplicate instances (Railway-compatible)
            # Method 1: Try 'ps aux' (works on most Unix systems including Railway)
            try:
                result = subprocess.run(
                    ['ps', 'aux'],
                    capture_output=True,
                    text=True,
                    timeout=3
                )
                if result.returncode == 0:
                    lines = result.stdout.split('\n')
                    for line in lines:
                        if 'run_websocket_collector_v2' in line and 'grep' not in line:
                            parts = line.split()
                            if len(parts) > 1:
                                try:
                                    pid = int(parts[1])
                                    if pid != current_pid:  # Don't count ourselves
                                        matching_pids.append(pid)
                                except (ValueError, IndexError):
                                    continue
            except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
                pass  # Try next method
            
            # Method 2: Try 'pgrep' (alternative method for Railway)
            if not matching_pids:
                try:
                    result = subprocess.run(
                        ['pgrep', '-f', 'run_websocket_collector_v2'],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    if result.returncode == 0:
                        for pid_str in result.stdout.strip().split('\n'):
                            if pid_str:
                                try:
                                    pid = int(pid_str.strip())
                                    if pid != current_pid:
                                        matching_pids.append(pid)
                                except ValueError:
                                    continue
                except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
                    pass  # Continue anyway
            
            # If duplicates found, automatically kill them
            if matching_pids:
                self.stdout.write(self.style.WARNING(
                    f'\n' + '='*70 + '\n'
                    f'⚠️  DUPLICATE INSTANCE DETECTED\n'
                    f'='*70 + '\n'
                    f'Found {len(matching_pids)} other instance(s) running (PIDs: {matching_pids})\n'
                    f'Current instance PID: {current_pid}\n'
                    f'This would cause duplicate logging and data collection.\n'
                    f'Auto-stopping duplicate instances...\n'
                ))
                
                killed_count = 0
                failed_pids = []
                
                for pid in matching_pids:
                    try:
                        # Verify process still exists before killing
                        os.kill(pid, 0)  # Signal 0 just checks if process exists
                        # Process exists, kill it
                        os.kill(pid, signal.SIGTERM)  # Graceful termination
                        killed_count += 1
                        self.stdout.write(self.style.SUCCESS(
                            f'✅ Stopped duplicate instance (PID: {pid})'
                        ))
                        # Give it a moment to terminate gracefully
                        time.sleep(0.5)
                    except ProcessLookupError:
                        # Process already dead, skip
                        self.stdout.write(self.style.NOTICE(
                            f'ℹ️  Process {pid} already terminated'
                        ))
                    except PermissionError:
                        # Don't have permission to kill (shouldn't happen, but handle gracefully)
                        failed_pids.append(pid)
                        self.stdout.write(self.style.ERROR(
                            f'❌ Permission denied killing PID {pid}'
                        ))
                    except Exception as e:
                        failed_pids.append(pid)
                        self.stdout.write(self.style.ERROR(
                            f'❌ Failed to stop PID {pid}: {e}'
                        ))
                
                # Summary
                self.stdout.write(self.style.SUCCESS(
                    f'\n📊 Cleanup Summary:\n'
                    f'   Stopped: {killed_count} instance(s)\n'
                    f'   Failed: {len(failed_pids)} instance(s)'
                ))
                
                if failed_pids:
                    self.stdout.write(self.style.WARNING(
                        f'   ⚠️  Could not stop PIDs: {failed_pids}\n'
                        f'   You may need to manually stop these processes'
                    ))
                
                self.stdout.write(self.style.SUCCESS(
                    f'\n✅ Continuing with current instance (PID: {current_pid})\n'
                    f'='*70 + '\n'
                ))
                
        except Exception as e:
            # If check fails completely, log but don't break functionality
            self.stdout.write(self.style.NOTICE(
                f'ℹ️  Could not check for duplicate instances: {e}\n'
                f'   Continuing anyway...'
            ))
        
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
        
        # Initialize Finnhub real-time news (optional - controlled by env flag and fails gracefully)
        if FINNHUB_SECOND_BY_SECOND_ENABLED:
            try:
                from api.management.commands.finnhub_realtime_v2 import initialize as init_finnhub
                if init_finnhub():
                    self.stdout.write(self.style.SUCCESS('📰 Finnhub real-time news enabled'))
                else:
                    self.stdout.write(self.style.NOTICE('📰 Finnhub disabled (API key not set or module unavailable)'))
            except Exception as e:
                self.stdout.write(self.style.NOTICE(f'📰 Finnhub disabled ({str(e)})'))
        else:
            self.stdout.write(self.style.NOTICE('📰 Finnhub real-time news disabled by config (FINNHUB_SECOND_BY_SECOND_ENABLED=false)'))

        # Initialize Tiingo real-time news (optional - controlled by env flag and fails gracefully)
        try:
            from api.management.commands.tiingo_realtime_news import initialize as init_tiingo
            if init_tiingo():
                self.stdout.write(self.style.SUCCESS('📰 Tiingo real-time news enabled'))
            else:
                self.stdout.write(self.style.NOTICE('📰 Tiingo disabled (ENABLE_TIINGO_NEWS=False or API key not set)'))
        except Exception as e:
            self.stdout.write(self.style.NOTICE(f'📰 Tiingo disabled ({str(e)})'))


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
        """Establish WebSocket connection with infinite retry and keepalive"""
        retry_count = 0
        max_backoff = 60  # Cap exponential backoff at 60 seconds

        while self.running:
            try:
                # Calculate backoff delay
                # OPTIMIZATION: If this is a reconnection after an established connection,
                # use minimal delay (2s) to reconnect immediately
                if retry_count > 0:
                    # Check if previous connection was established (before it closed)
                    was_connected_before = self.was_established_before_close
                    
                    if was_connected_before:
                        # Established connection dropped - reconnect immediately with minimal delay
                        delay = 2  # Just 2 seconds to allow graceful cleanup
                        self.stdout.write(self.style.WARNING(
                            f'⚡ FAST RECONNECT: Previous connection was established. Reconnecting in {delay}s...'
                        ))
                        # Reset flag after using it
                        self.was_established_before_close = False
                    else:
                        # Initial connection failed or handshake rejected - use exponential backoff
                        delay = min(2 ** retry_count, max_backoff)
                        self.stdout.write(self.style.WARNING(
                            f'⏳ Reconnecting in {delay}s (attempt #{retry_count + 1})...'
                        ))
                    
                    time.sleep(delay)

                self.stdout.write(self.style.WARNING('🔌 Connecting to EODHD WebSocket...'))

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
                import socket

                # CRITICAL: Enable WebSocket ping/pong keepalive to prevent idle timeout
                # OPTIMIZED: Balanced ping interval (20s) and lenient timeout (15s) to prevent false timeouts
                # The longer timeout prevents false positives from network latency or server processing delays
                self.stdout.write(self.style.SUCCESS('💓 Keepalive enabled: ping every 20s, timeout 15s'))
                self.ws.run_forever(
                    sslopt={"cert_reqs": ssl.CERT_NONE},
                    ping_interval=20,    # Send ping every 20 seconds (balanced: not too frequent, not too slow)
                    ping_timeout=15,     # Wait 15 seconds for pong response (lenient: prevents false timeouts)
                    ping_payload="keepalive"  # Optional payload
                )

                # If we reach here, connection closed (not an exception)
                # Track if this was an established connection before resetting the flag
                was_established = self.connection_established
                self.connection_established = False
                
                # Increment retry count for next iteration
                # Fast reconnect logic will check was_established_before_close flag
                retry_count += 1

            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING('🛑 Keyboard interrupt - stopping...'))
                self.running = False
                break

            except Exception as e:
                retry_count += 1
                error_str = str(e)
                error_type = type(e).__name__
                
                # Check if this is a ping/pong timeout exception
                is_timeout = ('timeout' in error_str.lower() or 
                             'timed out' in error_str.lower() or 
                             'WebSocketTimeoutException' in error_type or
                             'Timeout' in error_type)
                
                if is_timeout and self.connection_established:
                    # Ping/pong timeout on established connection - mark for fast reconnect
                    self.was_established_before_close = True
                    self.stdout.write(self.style.WARNING(
                        f'⏱️  Ping/pong timeout detected - marking for fast reconnect'
                    ))
                
                self.stdout.write(self.style.ERROR(
                    f'❌ Connection error ({error_type}): {e}'
                ))
                # Continue loop - will retry with backoff (fast reconnect if was_established_before_close is set)

        self.stdout.write(self.style.SUCCESS('✅ Connection loop exited'))
    
    def subscribe_to_symbol(self, symbol):
        """Subscribe to a single symbol"""
        try:
            subscribe_message = json.dumps({
                "action": "subscribe",
                "symbols": symbol
            })
            self.ws.send(subscribe_message)

            # Track subscription
            if symbol not in self.subscribed_symbols:
                self.subscribed_symbols.append(symbol)

            self.stdout.write(self.style.SUCCESS(f'✅ Subscribed to: {symbol}'))
            return True
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Subscribe failed for {symbol}: {e}'))
            return False

    def resubscribe_all(self):
        """CRITICAL: Resubscribe to all tracked symbols (required by EODHD after reconnect)"""
        if not self.subscribed_symbols:
            self.stdout.write(self.style.WARNING('⚠️  No previous subscriptions to restore'))
            return False

        try:
            # Batch subscribe (more efficient per EODHD docs)
            symbols_str = ",".join(self.subscribed_symbols)
            subscribe_message = json.dumps({
                "action": "subscribe",
                "symbols": symbols_str
            })
            self.ws.send(subscribe_message)

            self.stdout.write(self.style.SUCCESS(
                f'✅ Resubscribed to {len(self.subscribed_symbols)} symbols: {symbols_str}'
            ))
            return True
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Resubscribe failed: {e}'))
            return False

    def on_open(self, ws):
        """Called when WebSocket connection established"""
        self.connection_established = True
        self.last_connection_time = time.time()
        self.connection_start_time = time.time()
        self.total_connections += 1

        self.stdout.write(self.style.SUCCESS(
            f'✅ WebSocket connected! (Total connections: {self.total_connections})'
        ))

        # Enable TCP keepalive at socket level (backup for WebSocket ping)
        try:
            import socket
            # Get the underlying socket from the WebSocket connection
            if hasattr(ws, 'sock') and ws.sock and hasattr(ws.sock, 'socket'):
                sock = ws.sock.socket  # Get the actual socket object
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

                # Platform-specific TCP keepalive tuning (if available)
                if hasattr(socket, 'TCP_KEEPIDLE'):
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
                self.stdout.write(self.style.SUCCESS('💓 TCP keepalive enabled'))
        except Exception as e:
            # TCP keepalive is optional - WebSocket ping/pong is the primary mechanism
            if self.verbose:
                self.stdout.write(self.style.NOTICE(f'ℹ️  TCP keepalive not available (using WebSocket ping/pong only): {e}'))

        # Reset rate limit counter on successful connection
        if self.consecutive_429_errors > 0:
            self.stdout.write(self.style.SUCCESS(
                f'✅ Connection successful. Resetting rate limit counter (was: {self.consecutive_429_errors})'
            ))
            self.consecutive_429_errors = 0
            self.last_429_error_time = None

        # CRITICAL: Resubscribe if this is a reconnection, otherwise initial subscribe
        if self.subscribed_symbols:
            # This is a reconnection - resubscribe to existing symbols
            self.stdout.write(self.style.WARNING('🔄 Reconnection detected - resubscribing...'))
            self.resubscribe_all()
        else:
            # Initial connection - subscribe to symbol
            self.subscribe_to_symbol(self.symbol)

        self.stdout.write(self.style.WARNING('⏳ Waiting for server confirmation and data stream...'))

        # Start aggregation timer (only if not already running)
        if not hasattr(self, 'aggregation_thread') or self.aggregation_thread is None or not self.aggregation_thread.is_alive():
            self.aggregation_thread = threading.Thread(target=self.aggregation_loop, daemon=True)
            self.aggregation_thread.start()
            self.stdout.write(self.style.SUCCESS('⏱️  Aggregation timer started'))

        # Start async sentiment calculation thread (only if not already running)
        if not hasattr(self, 'sentiment_thread') or self.sentiment_thread is None or not self.sentiment_thread.is_alive():
            self.sentiment_running = True
            self.sentiment_thread = threading.Thread(target=self.sentiment_calculation_loop, daemon=True)
            self.sentiment_thread.start()
            self.stdout.write(self.style.SUCCESS('💚 Async sentiment calculator started'))

        # Start connection health monitoring thread (only if not already running)
        if not hasattr(self, 'heartbeat_thread') or self.heartbeat_thread is None or not self.heartbeat_thread.is_alive():
            self.heartbeat_thread = threading.Thread(target=self.health_monitor_loop, daemon=True)
            self.heartbeat_thread.start()
            self.stdout.write(self.style.SUCCESS('💓 Connection health monitor started'))

        # Start Finnhub news loop (non-blocking, optional, gated by config)
        if FINNHUB_SECOND_BY_SECOND_ENABLED:
            try:
                if not hasattr(self, 'news_thread') or self.news_thread is None or not self.news_thread.is_alive():
                    self.news_thread = threading.Thread(target=self.news_loop, daemon=True)
                    self.news_thread.start()
                    self.stdout.write(self.style.SUCCESS('📰 Finnhub news loop started (second-by-second)'))
            except Exception as e:
                # If Finnhub isn't configured or errors, log and continue without breaking collector
                self.stdout.write(self.style.NOTICE(f'📰 Finnhub news loop not started: {e}'))
        else:
            self.stdout.write(self.style.NOTICE('📰 Finnhub news loop disabled by config (FINNHUB_SECOND_BY_SECOND_ENABLED=false)'))

        # Start Tiingo news loop (non-blocking, optional, gated by env flag)
        try:
            from api.management.commands.tiingo_realtime_news import ENABLE_TIINGO_NEWS
            if ENABLE_TIINGO_NEWS:
                if not hasattr(self, 'tiingo_thread') or self.tiingo_thread is None or not self.tiingo_thread.is_alive():
                    self.tiingo_thread = threading.Thread(target=self.tiingo_news_loop, daemon=True)
                    self.tiingo_thread.start()
                    self.stdout.write(self.style.SUCCESS('📰 Tiingo news loop started (5-second polling)'))
            else:
                self.stdout.write(self.style.NOTICE('📰 Tiingo news loop disabled (ENABLE_TIINGO_NEWS=False)'))
        except Exception as e:
            # If Tiingo isn't configured or errors, log and continue without breaking collector
            self.stdout.write(self.style.NOTICE(f'📰 Tiingo news loop not started: {e}'))

    def sentiment_calculation_loop(self):
        """
        Async sentiment calculation loop - runs every second.
        Calculates sentiment in background without blocking aggregation loop.
        """
        self.stdout.write(self.style.SUCCESS('💚 Sentiment calculation loop started'))

        while self.sentiment_running and self.running:
            try:
                # Calculate sentiment every second
                from api.management.commands.sentiment_realtime_v2 import update_realtime_sentiment

                # Get last 60 seconds of snapshots for micro momentum
                recent_snapshots = list(SecondSnapshot.objects.filter(
                    ticker=self.ticker
                ).order_by('-timestamp')[:60])

                # Force macro recalc every minute (when second = 0)
                current_time = timezone.now()
                force_macro = (current_time.second == 0)

                # Calculate sentiment components
                sentiment_result = update_realtime_sentiment(
                    recent_snapshots,
                    ticker_symbol=self.symbol,
                    force_macro_recalc=force_macro
                )

                # Store in queue for aggregation loop to pick up
                with self.lock:
                    self.sentiment_queue.append({
                        'composite': sentiment_result.get('composite'),
                        'news': sentiment_result.get('news'),
                        'technical': sentiment_result.get('technical')
                    })

                # Log every 10 seconds
                if self.verbose or current_time.second % 10 == 0:
                    self.stdout.write(self.style.SUCCESS(
                        f'💚 Sentiment: Composite={sentiment_result.get("composite", 0):+.1f} '
                        f'[News={sentiment_result.get("news", 0):+.1f}, '
                        f'Tech={sentiment_result.get("technical", 0):+.1f}]'
                    ))

            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f'⚠️  Sentiment calculation error: {e}'
                ))
                if self.verbose:
                    import traceback
                    self.stdout.write(traceback.format_exc())

            # Sleep 1 second
            time.sleep(1)

        self.stdout.write(self.style.WARNING('💚 Sentiment calculation loop stopped'))

    def health_monitor_loop(self):
        """
        Monitor WebSocket connection health with faster detection.
        EODHD baseline: <50ms transport latency, so 15s without data = problem.
        Also enforces market hours by disconnecting after market close.
        """
        self.stdout.write(self.style.SUCCESS('💓 Health monitor loop started'))

        last_health_log = 0
        stale_threshold = 15  # Alert if no data for 15s (OPTIMIZED: was 60s)
        check_interval = 5    # Check every 5s (OPTIMIZED: was 10s)

        while self.running:
            try:
                current_time = time.time()

                # CRITICAL: Check market hours and disconnect if market is closed
                if self.connection_established and not self.skip_market_hours:
                    market_open, reason = self.is_market_open()
                    if not market_open:
                        self.stdout.write(self.style.WARNING(
                            f'🔔 Market closed during active connection: {reason}\n'
                            f'   Disconnecting to stop data collection...'
                        ))
                        self.running = False  # Stop the entire collector
                        if self.ws:
                            self.ws.close()
                        break

                # Check if we're connected and receiving data
                if self.connection_established:
                    # Calculate connection age
                    connection_age = None
                    if self.last_connection_time:
                        connection_age = current_time - self.last_connection_time
                    
                    if self.last_data_received_time:
                        time_since_last_data = current_time - self.last_data_received_time

                        # CRITICAL: Detect stale connections faster
                        # But be more lenient for NEW connections (first 30 seconds)
                        # New connections might take a few seconds to start receiving data
                        effective_threshold = stale_threshold
                        if connection_age and connection_age < 30:
                            # New connection - give it more time (30s grace period)
                            effective_threshold = 30
                            if time_since_last_data > effective_threshold:
                                self.stdout.write(self.style.ERROR(
                                    f'❌ STALE CONNECTION (NEW): No data for {time_since_last_data:.0f}s '
                                    f'(connection age: {connection_age:.0f}s, threshold: {effective_threshold}s)\n'
                                    f'   New connection never received data - likely subscription issue.\n'
                                    f'   Forcing reconnect...'
                                ))
                                if self.ws:
                                    self.ws.close()
                        elif time_since_last_data > effective_threshold:
                            self.stdout.write(self.style.ERROR(
                                f'❌ STALE CONNECTION: No data for {time_since_last_data:.0f}s (threshold: {effective_threshold}s)\n'
                                f'   EODHD baseline is <50ms latency - this connection is dead.\n'
                                f'   Forcing reconnect...'
                            ))
                            if self.ws:
                                self.ws.close()
                    elif connection_age and connection_age > 30:
                        # Connection established but never received data after 30 seconds
                        self.stdout.write(self.style.ERROR(
                            f'❌ STALE CONNECTION: Connection established {connection_age:.0f}s ago but never received data\n'
                            f'   Likely subscription issue or server problem.\n'
                            f'   Forcing reconnect...'
                        ))
                        if self.ws:
                            self.ws.close()

                    # Log health status every 60 seconds
                    if current_time - last_health_log >= 60:
                        uptime = current_time - self.connection_start_time if self.connection_start_time else 0
                        data_delay = current_time - self.last_data_received_time if self.last_data_received_time else 0

                        self.stdout.write(self.style.SUCCESS(
                            f'💓 Health Check:\n'
                            f'   Uptime: {uptime:.0f}s | Last data: {data_delay:.0f}s ago\n'
                            f'   Ticks: {self.total_ticks:,} | Candles: {self.total_1sec_candles:,}\n'
                            f'   Buffer: {len(self.tick_buffer_1sec)} seconds | Connections: {self.total_connections} | Disconnects: {self.total_disconnections}'
                        ))
                        last_health_log = current_time

            except Exception as e:
                self.stdout.write(self.style.WARNING(f'⚠️  Health monitor error: {e}'))

            # Check every 10 seconds (faster detection)
            time.sleep(check_interval)

        self.stdout.write(self.style.WARNING('💓 Health monitor loop stopped'))

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
                    error = finnhub_result.get('error')
                    if error == 'rate_limit_429':
                        # Rate limit hit - log it prominently
                        self.stdout.write(self.style.ERROR(
                            f'⚠️ RATE LIMIT: {finnhub_result.get("calls_last_minute", 0)} calls/min, '
                            f'{finnhub_result.get("consecutive_errors", 0)} consecutive errors'
                        ))
                    elif self.verbose:
                        self.stdout.write(self.style.WARNING(f'Finnhub query error: {error}'))

            except Exception as e:
                if self.verbose:
                    self.stdout.write(self.style.ERROR(f'❌ News loop error: {e}'))

            # Sleep 1.2 seconds (matches MIN_SECONDS_BETWEEN_CALLS in finnhub_realtime_v2.py)
            # This ensures we stay well under Finnhub's 60 calls/minute limit
            time.sleep(1.2)

    def tiingo_news_loop(self):
        """Run every 5 seconds to fetch Tiingo news (non-blocking)"""
        self.stdout.write(self.style.SUCCESS('📰 Tiingo news loop started'))

        # Tiingo loop runs independently of WebSocket state
        # Only check self.running flag (set to False when collector shuts down)
        while self.running:
            try:
                from api.management.commands.tiingo_realtime_news import query_tiingo_for_news

                # Query Tiingo (polls every 5 seconds, hybrid approach)
                # This function manages its own time windows and puts articles into a queue
                tiingo_result = query_tiingo_for_news()

                if tiingo_result.get('queued_for_scoring', 0) > 0:
                    self.stdout.write(self.style.SUCCESS(
                        f'📰 Tiingo: Queued {tiingo_result["queued_for_scoring"]} articles for scoring '
                        f'(found {tiingo_result.get("articles_found", 0)} total)'
                    ))
                elif tiingo_result.get('error'):
                    # ALWAYS log errors (not just in verbose mode)
                    self.stdout.write(self.style.ERROR(f'❌ Tiingo query error: {tiingo_result.get("error")}'))
                elif tiingo_result.get('reason') == 'disabled':
                    # Tiingo is disabled, stop the loop
                    self.stdout.write(self.style.NOTICE('📰 Tiingo disabled, stopping loop'))
                    break

            except Exception as e:
                # ALWAYS log errors - this is critical for diagnosing issues
                self.stdout.write(self.style.ERROR(f'❌ Tiingo news loop exception: {e}'))
                import traceback
                self.stdout.write(self.style.ERROR(f'   Traceback: {traceback.format_exc()}'))
                # Continue running even on errors

            # Sleep 5 seconds (Tiingo polling interval)
            time.sleep(5)

        self.stdout.write(self.style.NOTICE('📰 Tiingo news loop stopped'))

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
                        # Check if already processed using processed_seconds set
                        with self.lock:
                            already_processed = sec_to_process in self.processed_seconds
                        
                        if not already_processed:
                            self.aggregate_and_save_1sec_candle(sec_to_process)
                            self.last_processed_second = sec_to_process
                            processed_count += 1
                        else:
                            # Already processed - just clean up buffer
                            if self.verbose:
                                self.stdout.write(self.style.WARNING(
                                    f'⏭️  Skipping already processed second {sec_to_process}'
                                ))
                        
                        # Ensure key is removed from buffer even if we skipped processing
                        # (e.g. if we somehow processed it already but didn't clear it)
                        with self.lock:
                            if sec_to_process in self.tick_buffer_1sec:
                                del self.tick_buffer_1sec[sec_to_process]
                    
                    if processed_count > 0 and (loop_count % 10 == 0 or self.verbose):
                        self.stdout.write(self.style.SUCCESS(f'⚡ Processed {processed_count} seconds in this iteration'))
                    
                    # Cleanup old processed seconds (every 60 iterations = ~1 minute)
                    # Keep only last 5 minutes of processed seconds to prevent memory growth
                    if loop_count % 60 == 0:
                        with self.lock:
                            cutoff_second = current_second - 300  # 5 minutes ago
                            old_seconds = [s for s in self.processed_seconds if s < cutoff_second]
                            if old_seconds:
                                for old_sec in old_seconds:
                                    self.processed_seconds.discard(old_sec)
                                if self.verbose:
                                    self.stdout.write(self.style.NOTICE(
                                        f'🧹 Cleaned up {len(old_seconds)} old processed seconds (older than 5 minutes)'
                                    ))

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
        """Process incoming tick data with validation"""
        try:
            # Parse JSON
            try:
                data = json.loads(message)
            except json.JSONDecodeError as e:
                self.stdout.write(self.style.WARNING(
                    f'⚠️  Invalid JSON received: {message[:100]}... | Error: {e}'
                ))
                return

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

            # Validate required fields (per EODHD schema)
            if not symbol or price is None:
                self.stdout.write(self.style.WARNING(
                    f'⚠️  Incomplete tick data (missing symbol/price): {data}'
                ))
                return
            
            # REMOVED: Individual tick diagnostic logging (too verbose)
            # Only log first tick as milestone
            
            # Try bid/ask if no trade price (fallback)
            if price is None:
                price = data.get('bp', data.get('ap', None))
                if price is None:
                    self.stdout.write(self.style.WARNING(
                        f'⚠️  No valid price field found in data: {data}'
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
                    # REMOVED: Individual tick time difference logging (too verbose)
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'❌ Timestamp conversion error: {e}'))
                    dt = timezone.now()
            else:
                dt = timezone.now()
                # REMOVED: Individual tick timestamp warning (too verbose)

            # Update last data received time (for health monitoring)
            self.last_data_received_time = time.time()

            # Create in-memory tick object (NOT saved to database for performance)
            tick = {
                'price': float(price),
                'volume': int(volume),
                'timestamp': dt
            }
            
            # Add to buffers
            # Group ticks by their exact second (rounded down)
            tick_second = int(dt.timestamp())  # Get Unix timestamp as integer (second boundary)
            
            # BLOCK LATE TICKS: If this second has already been processed, skip 1-second buffer
            is_late_tick = False
            with self.lock:
                if tick_second in self.processed_seconds:
                    # This second was already closed and processed - skip 1-second buffer
                    is_late_tick = True
                    # OPTIMIZATION: Only log late ticks in verbose mode to reduce log spam
                    if self.verbose:
                        self.stdout.write(self.style.WARNING(
                            f'⏭️  LATE TICK: Second {tick_second} ({dt.strftime("%H:%M:%S")}) '
                            f'already processed. Skipping 1-second buffer. Delay: {(timezone.now() - dt).total_seconds():.1f}s'
                        ))
            
            # Only add to 1-second buffer if not a late tick
            if not is_late_tick:
                # LOCK ACQUIRE for writing to 1-second buffer
                with self.lock:
                    if tick_second not in self.tick_buffer_1sec:
                        self.tick_buffer_1sec[tick_second] = []
                    self.tick_buffer_1sec[tick_second].append(tick)
                # REMOVED: Individual buffer operation logging (too verbose)
            
            # Always add to 100-tick buffer (even late ticks can be part of 100-tick candles)
            self.tick_buffer_100tick.append(tick)
            self.tick_counter_100 += 1
            self.total_ticks += 1
            
            # Check if 100-tick candle completed
            if self.tick_counter_100 >= 100:
                self.create_100tick_candle()
                self.tick_counter_100 = 0
            
            # Summary tick logging (every 10 seconds, not individual ticks)
            self.ticks_since_last_log += 1
            current_time = time.time()
            if current_time - self.last_tick_log_time >= 10.0:  # Log summary every 10 seconds
                with self.lock:
                    buffer_size = len(self.tick_buffer_1sec)
                tick_rate = self.ticks_since_last_log / (current_time - self.last_tick_log_time)
                self.stdout.write(
                    f'📊 Ticks: {self.total_ticks:,} | Rate: {tick_rate:.1f}/s | '
                    f'Buffer: {buffer_size}s | Last: ${price:.2f} @ {dt.strftime("%H:%M:%S")}'
                )
                self.last_tick_log_time = current_time
                self.ticks_since_last_log = 0

        except Exception as e:
            # Never crash on bad data - log and continue
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
        # Create timestamp from the second boundary (not from tick timestamps)
        try:
            timestamp = datetime.fromtimestamp(second_timestamp, tz=pytz.UTC)
        except Exception as e:
             self.stdout.write(self.style.ERROR(f'❌ Error converting timestamp {second_timestamp}: {e}'))
             return
        
        # STRICT DUPLICATE PREVENTION: Check if already processed (fast in-memory check)
        with self.lock:
            if second_timestamp in self.processed_seconds:
                self.stdout.write(self.style.WARNING(
                    f'⚠️  SecondSnapshot SKIPPED: Second {second_timestamp} ({timestamp.strftime("%H:%M:%S")}) '
                    f'already processed (in-memory check)'
                ))
                return
        
        # Also check database (slower but catches edge cases)
        existing = SecondSnapshot.objects.filter(
            ticker=self.ticker,
            timestamp=timestamp
        ).first()
        
        if existing:
            # Already exists in DB - mark as processed and skip
            with self.lock:
                self.processed_seconds.add(second_timestamp)
            self.stdout.write(self.style.WARNING(
                f'⚠️  SecondSnapshot SKIPPED: {timestamp.strftime("%H:%M:%S")} already exists in database'
            ))
            return
        
        # Get ticks for this specific second and remove from buffer
        # LOCK ACQUIRE for popping
        with self.lock:
            ticks = self.tick_buffer_1sec.pop(second_timestamp, [])
        
        # DIAGNOSTIC: Always log what we're trying to process
        if True: # Always log for now to debug
             self.stdout.write(self.style.NOTICE(
                f'🔧 SecondSnapshot ATTEMPT: Processing second {second_timestamp} ({timestamp.strftime("%H:%M:%S")}), '
                f'Found {len(ticks)} ticks in buffer'
            ))
        
        try:
            if not ticks:
                # No ticks for this second - we still want to create a candle if it's during market hours
                # using the CLOSE of the previous candle (forward fill)
                # BUT for now, let's just return to match previous logic.
                self.stdout.write(self.style.WARNING(
                    f'⚠️  SecondSnapshot SKIPPED: No ticks for second {timestamp.strftime("%H:%M:%S")} (ts={second_timestamp})'
                ))
                return

            # Calculate OHLCV from tick dicts (not ORM objects)
            open_price = float(ticks[0]['price'])
            high_price = max(float(t['price']) for t in ticks)
            low_price = min(float(t['price']) for t in ticks)
            close_price = float(ticks[-1]['price'])
            total_volume = sum(int(t['volume']) for t in ticks)
            tick_count = len(ticks)
            
            # ============================================================
            # REAL-TIME SENTIMENT SCORING V2 (ASYNC - Non-blocking)
            # ============================================================
            # Check if we have a pre-calculated sentiment from async thread
            sentiment_scores = {
                'composite': None,
                'news': None,
                'technical': None
            }

            # Try to get latest sentiment from queue (non-blocking)
            try:
                with self.lock:
                    if self.sentiment_queue:
                        # Get most recent sentiment result
                        sentiment_scores = self.sentiment_queue[-1]
                        if self.verbose and self.total_1sec_candles % 10 == 0:
                            self.stdout.write(self.style.SUCCESS(
                                f'💚 Using cached sentiment: '
                                f'Composite={sentiment_scores.get("composite", 0):+.1f}'
                            ))
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f'⚠️  Could not retrieve sentiment from queue: {e}'
                ))

            # ============================================================
            
            # Save to SecondSnapshot with exact second boundary timestamp
            # Sentiment scores are included if calculated successfully, otherwise NULL
            # ROBUST ERROR HANDLING: Retry up to 3 times with exponential backoff
            max_retries = 3
            retry_delay = 0.1  # Start with 100ms

            for attempt in range(max_retries):
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
                        composite_score=sentiment_scores.get('composite'),
                        news_score_cached=sentiment_scores.get('news'),
                        technical_score_cached=sentiment_scores.get('technical'),
                        source='eodhd_ws'
                    )

                    self.total_1sec_candles += 1
                    self.last_second_timestamp = timestamp

                    # Mark this second as processed to prevent duplicates
                    with self.lock:
                        self.processed_seconds.add(second_timestamp)

                    # ALWAYS LOG successful creation
                    self.stdout.write(self.style.SUCCESS(
                        f'✅ SecondSnapshot #{self.total_1sec_candles}: '
                        f'{timestamp.strftime("%H:%M:%S")} | '
                        f'O:{open_price:.2f} H:{high_price:.2f} L:{low_price:.2f} C:{close_price:.2f} | '
                        f'{tick_count} ticks'
                    ))

                    # Success! Break out of retry loop
                    break

                except Exception as create_error:
                    if attempt < max_retries - 1:
                        # Not the last attempt - retry with backoff
                        self.stdout.write(self.style.WARNING(
                            f'⚠️  SecondSnapshot creation failed (attempt {attempt + 1}/{max_retries}): {create_error}. '
                            f'Retrying in {retry_delay:.2f}s...'
                        ))
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        # Last attempt failed - log error but DON'T crash the thread
                        self.stdout.write(self.style.ERROR(
                            f'❌ SecondSnapshot CREATION FAILED after {max_retries} attempts:\n'
                            f'   Timestamp: {timestamp}\n'
                            f'   Error: {create_error}\n'
                            f'   Data: O={open_price}, H={high_price}, L={low_price}, C={close_price}, V={total_volume}'
                        ))
                        import traceback
                        self.stdout.write(self.style.ERROR(traceback.format_exc()))
                        # Mark as processed anyway to avoid infinite retries
                        with self.lock:
                            self.processed_seconds.add(second_timestamp)

        except Exception as e:
            # Catch-all for any unexpected errors - log but DON'T crash
            self.stdout.write(self.style.ERROR(
                f'❌ SecondSnapshot PROCESS ERROR: {e}\n'
                f'   Second: {second_timestamp}'
            ))
            import traceback
            self.stdout.write(self.style.ERROR(traceback.format_exc()))
            # Mark as processed to avoid getting stuck
            with self.lock:
                self.processed_seconds.add(second_timestamp)
    
    def create_100tick_candle(self):
        """Create 100-tick candle from buffer (using in-memory tick dicts)"""
        if len(self.tick_buffer_100tick) < 100:
            return

        try:
            # Get last 100 ticks
            ticks = list(self.tick_buffer_100tick)[-100:]

            # Calculate OHLCV from tick dicts
            open_price = float(ticks[0]['price'])
            high_price = max(float(t['price']) for t in ticks)
            low_price = min(float(t['price']) for t in ticks)
            close_price = float(ticks[-1]['price'])
            total_volume = sum(int(t['volume']) for t in ticks)

            first_tick_time = ticks[0]['timestamp']
            last_tick_time = ticks[-1]['timestamp']
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
        """Handle WebSocket errors (with thread-safe duplicate prevention and diagnostics)"""
        # THREAD-SAFE: Prevent duplicate error logging
        with self.error_log_lock:
            if self.error_logged:
                return  # Already logged, skip duplicate
            self.error_logged = True

        error_str = str(error)
        current_time = time.time()

        # Gather diagnostics
        time_since_last_data = None
        if self.last_data_received_time:
            time_since_last_data = current_time - self.last_data_received_time

        self.stdout.write(self.style.ERROR(
            '\n' + '='*70 + '\n'
            '❌ WEBSOCKET ERROR EVENT\n'
            '='*70 + '\n'
            f'Error Details: {error}\n'
            f'Error Type: {type(error).__name__}\n'
            f'Connection State: {"ESTABLISHED" if self.connection_established else "NOT ESTABLISHED"}\n'
        ))

        # Detect 429 rate limiting errors
        if '429' in error_str or 'Too Many Requests' in error_str:
            self.consecutive_429_errors += 1
            self.last_429_error_time = current_time

            if self.connection_established:
                self.stdout.write(self.style.ERROR(
                    f'🚫 Error Category: RATE LIMIT (429) - Server closed ESTABLISHED connection\n'
                    f'   Reason: Too many requests detected by server\n'
                    f'   Consecutive 429 errors: {self.consecutive_429_errors}\n'
                    f'   Connection was active before this error'
                ))
            else:
                self.stdout.write(self.style.ERROR(
                    f'🚫 Error Category: RATE LIMIT (429) - Connection HANDSHAKE REJECTED\n'
                    f'   Reason: Server rejected connection attempt due to rate limiting\n'
                    f'   Consecutive 429 errors: {self.consecutive_429_errors}\n'
                    f'   Connection never established'
                ))
            
            if time_since_last_data:
                self.stdout.write(self.style.ERROR(
                    f'   ⏰ Time since last data: {time_since_last_data:.1f} seconds'
                ))

        # Log other common disconnection causes
        elif '502' in error_str or 'Bad Gateway' in error_str:
            self.stdout.write(self.style.WARNING(
                f'🚫 Error Category: SERVER ERROR (502 Bad Gateway)\n'
                f'   Reason: Server is overloaded or undergoing maintenance\n'
                f'   Connection state: {"ESTABLISHED" if self.connection_established else "NOT ESTABLISHED"}'
            ))
        elif '503' in error_str or 'Service Unavailable' in error_str:
            self.stdout.write(self.style.WARNING(
                f'🚫 Error Category: SERVER ERROR (503 Service Unavailable)\n'
                f'   Reason: Server temporarily unavailable\n'
                f'   Connection state: {"ESTABLISHED" if self.connection_established else "NOT ESTABLISHED"}'
            ))
        elif 'timeout' in error_str.lower() or 'timed out' in error_str.lower() or 'WebSocketTimeoutException' in error_str:
            # Detect ping/pong timeout specifically
            is_ping_pong_timeout = 'ping' in error_str.lower() or 'pong' in error_str.lower() or 'WebSocketTimeoutException' in error_str
            
            if is_ping_pong_timeout:
                self.stdout.write(self.style.WARNING(
                    f'🚫 Error Category: PING/PONG TIMEOUT\n'
                    f'   Reason: Server did not respond to ping within timeout period (15s)\n'
                    f'   This may indicate network latency or server processing delay\n'
                    f'   Connection will be closed and reconnected automatically\n'
                    f'   Connection state: {"ESTABLISHED" if self.connection_established else "NOT ESTABLISHED"}'
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f'🚫 Error Category: CONNECTION TIMEOUT\n'
                    f'   Reason: Network or server did not respond in time\n'
                    f'   Connection state: {"ESTABLISHED" if self.connection_established else "NOT ESTABLISHED"}'
                ))
            
            if time_since_last_data:
                self.stdout.write(self.style.WARNING(
                    f'   ⏰ Time since last data: {time_since_last_data:.1f} seconds'
                ))
            
            # For ping/pong timeouts, mark connection for fast reconnect if it was established
            if is_ping_pong_timeout and self.connection_established:
                self.was_established_before_close = True
                self.stdout.write(self.style.SUCCESS(
                    f'   ✅ Marked for fast reconnect (connection was established before timeout)'
                ))
        elif 'SSL' in error_str or 'TLS' in error_str or 'certificate' in error_str.lower():
            self.stdout.write(self.style.ERROR(
                f'🚫 Error Category: SSL/TLS ERROR\n'
                f'   Reason: Certificate or encryption issue\n'
                f'   Connection state: {"ESTABLISHED" if self.connection_established else "NOT ESTABLISHED"}'
            ))
        elif 'Connection refused' in error_str or 'Connection reset' in error_str:
            self.stdout.write(self.style.WARNING(
                f'🚫 Error Category: NETWORK ERROR\n'
                f'   Reason: Connection refused or reset by server\n'
                f'   Connection state: {"ESTABLISHED" if self.connection_established else "NOT ESTABLISHED"}'
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f'🚫 Error Category: UNKNOWN\n'
                f'   Connection state: {"ESTABLISHED" if self.connection_established else "NOT ESTABLISHED"}'
            ))
            if time_since_last_data:
                self.stdout.write(self.style.WARNING(
                    f'   ⏰ Time since last data: {time_since_last_data:.1f} seconds'
                ))

        # Connection metrics
        if self.connection_established:
            self.stdout.write(self.style.WARNING(
                f'📊 Connection Metrics:\n'
                f'   Total ticks: {self.total_ticks:,}\n'
                f'   SecondSnapshots: {self.total_1sec_candles:,}'
            ))

        self.stdout.write(self.style.ERROR('='*70 + '\n'))

        # Reset flag after 5 seconds (longer to prevent duplicates)
        threading.Timer(5.0, lambda: setattr(self, 'error_logged', False)).start()
    
    def on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close (with thread-safe duplicate prevention and comprehensive diagnostics)"""
        # THREAD-SAFE: Prevent duplicate disconnect logging with timestamp check
        current_time = time.time()
        with self.disconnect_log_lock:
            # Check if we're already processing a close event
            if self._closing_in_progress:
                return  # Already handling a close, skip duplicate
            
            # Check if we've logged a disconnect in the last 10 seconds (more robust)
            if self.disconnect_logged and current_time - self._last_disconnect_log_time < 10.0:
                return  # Too soon, skip duplicate
            
            # Mark as processing and logged
            self._closing_in_progress = True
            self.disconnect_logged = True
            self._last_disconnect_log_time = current_time

        self.total_disconnections += 1

        # CRITICAL: Store if connection was established BEFORE resetting flag (for fast reconnect)
        was_connected = self.connection_established
        if was_connected:
            self.was_established_before_close = True  # Mark for fast reconnect logic

        # Gather comprehensive diagnostics BEFORE logging
        connection_duration = None
        time_since_last_data = None
        time_since_connection = None
        
        current_time = time.time()
        
        if self.last_connection_time:
            connection_duration = current_time - self.last_connection_time
            time_since_connection = current_time - self.last_connection_time
        
        if self.last_data_received_time:
            time_since_last_data = current_time - self.last_data_received_time
        
        # Calculate tick rate during this connection
        tick_rate = None
        if was_connected and connection_duration and connection_duration > 0:
            # Estimate ticks during this connection (approximate)
            tick_rate = self.total_ticks / connection_duration if connection_duration > 0 else None

        # Determine disconnection reason
        disconnect_reason = "UNKNOWN"
        disconnect_category = "UNKNOWN"
        
        # Check for rate limiting first (takes precedence)
        if self.consecutive_429_errors > 0:
            disconnect_reason = f"Rate limit (429) - {self.consecutive_429_errors} consecutive errors"
            disconnect_category = "RATE_LIMIT"
        elif close_status_code:
            if close_status_code == 1000:
                disconnect_reason = "Normal closure (1000)"
                disconnect_category = "NORMAL"
            elif close_status_code == 1001:
                disconnect_reason = "Going away (1001) - Server shutdown or client navigation"
                disconnect_category = "SERVER_SHUTDOWN"
            elif close_status_code == 1006:
                disconnect_reason = "Abnormal closure (1006) - No close frame received"
                disconnect_category = "ABNORMAL"
            elif close_status_code == 1008:
                disconnect_reason = "Policy violation (1008) - Server rejected connection"
                disconnect_category = "POLICY_VIOLATION"
            elif close_status_code == 1011:
                disconnect_reason = "Server error (1011) - Internal server error"
                disconnect_category = "SERVER_ERROR"
            elif close_status_code == 1012:
                disconnect_reason = "Service restart (1012) - Server restarting"
                disconnect_category = "SERVER_RESTART"
            elif close_status_code == 1013:
                disconnect_reason = "Try again later (1013) - Server overloaded"
                disconnect_category = "SERVER_OVERLOAD"
            elif close_status_code == 1014:
                disconnect_reason = "Bad gateway (1014) - Gateway error"
                disconnect_category = "GATEWAY_ERROR"
            elif close_status_code == 1015:
                disconnect_reason = "TLS handshake failure (1015)"
                disconnect_category = "TLS_ERROR"
            else:
                disconnect_reason = f"Close code {close_status_code}"
                disconnect_category = "OTHER"
        else:
            # No close code - abnormal closure
            if was_connected:
                if time_since_last_data and time_since_last_data > 15:
                    disconnect_reason = "Idle timeout - No data received for >15 seconds"
                    disconnect_category = "IDLE_TIMEOUT"
                elif time_since_last_data and time_since_last_data > 5:
                    disconnect_reason = "Network drop - No data received for >5 seconds"
                    disconnect_category = "NETWORK_DROP"
                else:
                    disconnect_reason = "Abnormal closure - Connection closed without close frame"
                    disconnect_category = "ABNORMAL"
            else:
                disconnect_reason = "Handshake failed - Connection never established"
                disconnect_category = "HANDSHAKE_FAILED"

        # Check for rate limiting context
        rate_limit_context = ""
        if self.consecutive_429_errors > 0:
            rate_limit_context = f" | Rate limit errors: {self.consecutive_429_errors}"
            if self.last_429_error_time:
                time_since_429 = current_time - self.last_429_error_time
                rate_limit_context += f" (last {time_since_429:.1f}s ago)"

        # Log comprehensive diagnostics
        self.stdout.write(self.style.WARNING(
            '\n' + '='*70 + '\n'
            '🔌 WEBSOCKET DISCONNECTION EVENT\n'
            '='*70 + '\n'
        ))

        # Connection status
        if was_connected:
            self.stdout.write(self.style.WARNING(
                f'📊 Connection Status: ESTABLISHED connection was CLOSED\n'
                f'⏱️  Connection Duration: {connection_duration:.1f} seconds\n'
                f'📈 Ticks Collected: {self.total_ticks:,}'
            ))
            if tick_rate:
                self.stdout.write(self.style.WARNING(
                    f'📊 Tick Rate: {tick_rate:.1f} ticks/second'
                ))
        else:
            self.stdout.write(self.style.WARNING(
                f'📊 Connection Status: HANDSHAKE FAILED (connection never established)\n'
                f'❌ Could not complete WebSocket handshake with server'
            ))

        # Close code and message
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

        # Disconnection reason and category
        self.stdout.write(self.style.ERROR(
            f'🔍 Disconnection Reason: {disconnect_reason}\n'
            f'📋 Category: {disconnect_category}'
        ))

        # Data flow diagnostics
        if was_connected:
            self.stdout.write(self.style.WARNING(
                f'📊 Data Flow Diagnostics:'
            ))
            if time_since_last_data is not None:
                self.stdout.write(self.style.WARNING(
                    f'   ⏰ Time since last data: {time_since_last_data:.1f} seconds'
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f'   ⏰ Time since last data: Never received data'
                ))
            
            self.stdout.write(self.style.WARNING(
                f'   📈 SecondSnapshots created: {self.total_1sec_candles:,}\n'
                f'   🎯 100-tick candles created: {self.total_100tick_candles:,}'
            ))
            
            with self.lock:
                buffer_size = len(self.tick_buffer_1sec)
            self.stdout.write(self.style.WARNING(
                f'   📦 Ticks in buffer: {buffer_size} seconds'
            ))

        # Rate limiting context
        if rate_limit_context:
            self.stdout.write(self.style.ERROR(
                f'🚫 Rate Limit Context:{rate_limit_context}'
            ))

        # Connection history
        self.stdout.write(self.style.WARNING(
            f'🔄 Connection History: Total connections: {self.total_connections} | '
            f'Total disconnections: {self.total_disconnections}'
        ))

        # Recommendations based on disconnect category
        if disconnect_category == "IDLE_TIMEOUT":
            self.stdout.write(self.style.WARNING(
                f'💡 Recommendation: Connection idle timeout detected. '
                f'Consider checking ping/pong keepalive settings.'
            ))
        elif disconnect_category == "RATE_LIMIT" or self.consecutive_429_errors > 0:
            self.stdout.write(self.style.ERROR(
                f'💡 Recommendation: Rate limiting detected. '
                f'Reduce connection frequency or check API subscription limits.'
            ))
        elif disconnect_category == "NETWORK_DROP":
            self.stdout.write(self.style.WARNING(
                f'💡 Recommendation: Network instability detected. '
                f'Check network connectivity and firewall settings.'
            ))
        elif disconnect_category == "SERVER_ERROR" or disconnect_category == "SERVER_OVERLOAD":
            self.stdout.write(self.style.WARNING(
                f'💡 Recommendation: Server-side issue detected. '
                f'This is likely temporary - will retry with backoff.'
            ))

        self.stdout.write(self.style.WARNING('='*70 + '\n'))

        # Reset connection state
        self.connection_established = False

        # Reset flags after 10 seconds (longer to prevent duplicates)
        def reset_flags():
            with self.disconnect_log_lock:
                self.disconnect_logged = False
                self._closing_in_progress = False
        
        threading.Timer(10.0, reset_flags).start()
    
    def cleanup(self):
        """Cleanup and display statistics"""
        self.stdout.write(self.style.WARNING('\n🧹 Starting cleanup...'))

        # Stop sentiment calculation thread
        self.sentiment_running = False
        if self.sentiment_thread and self.sentiment_thread.is_alive():
            self.stdout.write(self.style.NOTICE('⏳ Waiting for sentiment thread to stop...'))
            self.sentiment_thread.join(timeout=5.0)

        # Process any remaining ticks for all seconds in buffer
        # LOCK ACQUIRE for key listing
        with self.lock:
            keys = sorted(self.tick_buffer_1sec.keys())

        if keys:
            self.stdout.write(self.style.NOTICE(f'⏳ Processing {len(keys)} remaining seconds in buffer...'))
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
