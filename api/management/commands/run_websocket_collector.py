"""
EODHD WebSocket Data Collector
Connects to EODHD WebSocket API and collects real-time price ticks
Stores second-by-second price data to OHLCVTick table

Run with: python manage.py run_websocket_collector
"""

import os
import json
import time
import signal
import sys
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from api.models import Ticker, OHLCVTick
from dotenv import load_dotenv

# Load environment variables
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

# Symbols to track (NASDAQ Composite Index)
# EODHD uses "COMP" for NASDAQ Composite Index
# Note: Some subscription plans may only support stocks, not indexes
SYMBOLS = ["COMP"]


class Command(BaseCommand):
    help = 'Collect real-time price data from EODHD WebSocket'
    
    def __init__(self):
        super().__init__()
        self.ws = None
        self.nasdaq_ticker = None
        self.running = True
        self.tick_count = 0
        self.last_tick_time = None
        self.connection_start = None
        
    def add_arguments(self, parser):
        parser.add_argument(
            '--symbol',
            type=str,
            default='COMP',
            help='Symbol to track (default: COMP for NASDAQ Composite on EODHD)'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Print every tick (default: print every 10th tick)'
        )
        
    def handle(self, *args, **options):
        # Get options
        symbol = options.get('symbol', 'COMP')
        self.verbose = options.get('verbose', False)
        
        # Validate API key
        if not EODHD_API_KEY:
            self.stdout.write(self.style.ERROR(
                '❌ EODHD_API_KEY not set in .env file\n'
                '   Add it to your .env file: EODHD_API_KEY=your_key_here'
            ))
            return
        
        # Get or create NASDAQ ticker
        self.nasdaq_ticker, created = Ticker.objects.get_or_create(
            symbol='^IXIC',
            defaults={
                'company_name': 'NASDAQ Composite Index',
                'exchange': 'NASDAQ'
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'✨ Created ticker: ^IXIC'))
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # Display startup info
        self.stdout.write(self.style.SUCCESS(
            '\n' + '='*70 + '\n'
            '🚀 EODHD WebSocket Collector\n'
            '='*70
        ))
        self.stdout.write(f'📊 Ticker: ^IXIC (NASDAQ Composite)')
        self.stdout.write(f'🔗 WebSocket: wss://ws.eodhistoricaldata.com/ws/us')
        self.stdout.write(f'📡 Subscribing to: {symbol}')
        self.stdout.write(f'💾 Database: Storing to OHLCVTick table')
        self.stdout.write('⌨️  Press Ctrl+C to stop\n')
        
        # Start WebSocket connection with auto-reconnect
        self.connection_start = time.time()
        try:
            while self.running:
                try:
                    self.connect_and_run(symbol)
                except KeyboardInterrupt:
                    self.running = False
                    break
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'\n❌ Error: {e}'))
                    if self.running:
                        self.stdout.write('🔄 Reconnecting in 5 seconds...')
                        time.sleep(5)
        finally:
            self.cleanup()
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.stdout.write(self.style.WARNING('\n\n⚠️  Received shutdown signal...'))
        self.running = False
        if self.ws:
            self.ws.close()
    
    def connect_and_run(self, symbol):
        """Establish WebSocket connection and handle messages"""
        self.stdout.write(self.style.WARNING('🔌 Connecting to EODHD WebSocket...'))
        
        # Create WebSocket app
        self.ws = websocket.WebSocketApp(
            WEBSOCKET_URL,
            on_open=lambda ws: self.on_open(ws, symbol),
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        
        # Disable SSL verification for macOS compatibility
        # Note: This is acceptable for testing. For production, install certificates:
        # /Applications/Python\ 3.XX/Install\ Certificates.command
        import ssl
        self.stdout.write(self.style.WARNING('⚠️  Running without SSL verification (OK for testing)'))
        self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})
    
    def on_open(self, ws, symbol):
        """Called when WebSocket connection is established"""
        self.stdout.write(self.style.SUCCESS('✅ WebSocket connected!'))
        
        # Subscribe to symbol
        # EODHD subscription format: {"action": "subscribe", "symbols": "AAPL,MSFT"}
        subscribe_message = {
            "action": "subscribe",
            "symbols": symbol
        }
        
        ws.send(json.dumps(subscribe_message))
        self.stdout.write(self.style.SUCCESS(f'📡 Subscribed to {symbol}'))
        self.stdout.write(self.style.WARNING('⏳ Waiting for data...\n'))
    
    def on_message(self, ws, message):
        """Called when a message is received from WebSocket"""
        try:
            # Parse JSON message
            data = json.loads(message)
            
            # Handle different message types
            # EODHD sends different message formats:
            # 1. Trade data: {"s": "AAPL", "p": 150.25, "v": 100, "t": 1234567890}
            # 2. Quote data: {"s": "AAPL", "bp": 150.25, "ap": 150.26, "t": 1234567890}
            # 3. Status messages: {"status": "connected"}
            # 4. Error messages: {"error": "message"}
            
            # Check for error messages
            if 'error' in data:
                error_msg = data.get('error', '')
                self.stdout.write(self.style.ERROR(f'❌ Server error: {error_msg}'))
                # Print full message for debugging
                self.stdout.write(f'   Full message: {message}')
                return
            
            # Check for status messages
            if 'status' in data:
                status = data.get('status', '')
                self.stdout.write(self.style.SUCCESS(f'📢 Status: {status}'))
                return
            
            # Check for subscription confirmation
            if 'message' in data:
                msg = data.get('message', '')
                self.stdout.write(self.style.SUCCESS(f'📢 Message: {msg}'))
                # If it's an authorization message, we're good
                if 'authorized' in msg.lower():
                    self.stdout.write(self.style.SUCCESS('✅ Subscription active, waiting for data...'))
                return
            
            # Extract trade/quote data
            symbol = data.get('s', '')
            price = data.get('p', None)  # Trade price
            volume = data.get('v', 0)
            timestamp_unix = data.get('t', None)
            
            # If no trade price, try quote price
            if price is None:
                price = data.get('bp', None)  # Bid price
                if price is None:
                    price = data.get('ap', None)  # Ask price
            
            # Extract bid/ask if available
            bid = data.get('bp', None)
            ask = data.get('ap', None)
            
            # Validate we have minimum required data
            if not symbol or price is None:
                # Unknown message format - print for debugging if verbose
                if self.verbose:
                    self.stdout.write(self.style.WARNING(f'⚠️  Unknown message format: {message[:200]}'))
                return
            
            # Convert timestamp (Unix epoch in milliseconds to datetime)
            if timestamp_unix:
                try:
                    # EODHD usually sends timestamp in milliseconds
                    if timestamp_unix > 10000000000:  # Milliseconds
                        timestamp_unix = timestamp_unix / 1000
                    dt = datetime.fromtimestamp(timestamp_unix, tz=timezone.utc)
                except Exception:
                    dt = timezone.now()
            else:
                dt = timezone.now()
            
            # Save to database
            tick = OHLCVTick.objects.create(
                ticker=self.nasdaq_ticker,
                timestamp=dt,
                price=price,
                volume=volume,
                bid=bid,
                ask=ask,
                source='eodhd_ws'
            )
            
            self.tick_count += 1
            self.last_tick_time = dt
            
            # Log based on verbosity
            if self.verbose or self.tick_count % 10 == 0:
                bid_ask_str = ''
                if bid and ask:
                    bid_ask_str = f' | Bid: ${bid:.2f} Ask: ${ask:.2f}'
                
                self.stdout.write(
                    f'💾 Tick #{self.tick_count:>6}: {dt.strftime("%H:%M:%S")} | '
                    f'${price:>8.2f} | Vol: {volume:>8,}{bid_ask_str}'
                )
        
        except json.JSONDecodeError:
            # Not a JSON message, might be a status message
            self.stdout.write(self.style.WARNING(f'⚠️  Non-JSON message: {message[:100]}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error processing message: {e}'))
            # Print the raw message for debugging
            self.stdout.write(f'   Raw message: {message[:200]}')
    
    def on_error(self, ws, error):
        """Called when WebSocket encounters an error"""
        self.stdout.write(self.style.ERROR(f'❌ WebSocket error: {error}'))
    
    def on_close(self, ws, close_status_code, close_msg):
        """Called when WebSocket connection is closed"""
        if close_status_code:
            self.stdout.write(self.style.WARNING(
                f'⚠️  WebSocket closed (code: {close_status_code}, msg: {close_msg})'
            ))
        else:
            self.stdout.write(self.style.WARNING('⚠️  WebSocket closed'))
    
    def cleanup(self):
        """Cleanup and display statistics"""
        if self.ws:
            self.ws.close()
        
        # Calculate statistics
        uptime = time.time() - self.connection_start if self.connection_start else 0
        uptime_str = f"{int(uptime // 60)}m {int(uptime % 60)}s"
        
        self.stdout.write(self.style.SUCCESS(
            f'\n' + '='*70 + '\n'
            f'📊 Session Statistics\n'
            f'='*70 + '\n'
            f'   Total ticks collected: {self.tick_count:,}\n'
            f'   Uptime: {uptime_str}\n'
            f'   Last tick: {self.last_tick_time.strftime("%Y-%m-%d %H:%M:%S") if self.last_tick_time else "N/A"}\n'
            f'='*70
        ))
        self.stdout.write(self.style.SUCCESS('✅ Collector stopped cleanly'))

