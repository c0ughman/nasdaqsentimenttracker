"""
Management command to sync all tickers from news sources to database.

This ensures all tickers referenced by Finnhub and Tiingo news collectors
exist in the database, preventing articles from being misattributed to QLD.

Run with: python manage.py sync_all_tickers
"""

from django.core.management.base import BaseCommand
from api.models import Ticker
from api.management.commands.finnhub_realtime_v2 import WATCHLIST
from api.management.commands.tiingo_realtime_news import TOP_TICKERS, MARKET_INDICES, SECTOR_ETFS
from api.management.commands.nasdaq_config import COMPANY_NAMES


class Command(BaseCommand):
    help = 'Sync all tickers from news sources to database (prevents QLD fallback)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        
        # Collect all unique tickers from all sources
        all_tickers = set()
        
        # From Finnhub watchlist
        all_tickers.update(WATCHLIST)
        
        # From Tiingo
        all_tickers.update(TOP_TICKERS)
        all_tickers.update(MARKET_INDICES)
        all_tickers.update(SECTOR_ETFS)
        
        # Ensure QLD exists (critical fallback)
        all_tickers.add('QLD')
        
        # Sort for consistent output
        all_tickers = sorted(all_tickers)
        
        self.stdout.write(self.style.SUCCESS(
            f'\n{"="*70}\n'
            f'📊 Syncing {len(all_tickers)} tickers to database\n'
            f'{"="*70}\n'
        ))
        
        created_count = 0
        existing_count = 0
        skipped_count = 0
        
        # Company name mappings (expand as needed)
        company_name_map = {
            # From nasdaq_config
            **COMPANY_NAMES,
            
            # Additional NASDAQ-100 tickers
            'AMGN': 'Amgen Inc.',
            'HON': 'Honeywell International Inc.',
            'AMAT': 'Applied Materials Inc.',
            'SBUX': 'Starbucks Corporation',
            'ISRG': 'Intuitive Surgical Inc.',
            'BKNG': 'Booking Holdings Inc.',
            'ADP': 'Automatic Data Processing Inc.',
            'GILD': 'Gilead Sciences Inc.',
            'ADI': 'Analog Devices Inc.',
            'VRTX': 'Vertex Pharmaceuticals Inc.',
            'MDLZ': 'Mondelez International Inc.',
            'REGN': 'Regeneron Pharmaceuticals Inc.',
            'LRCX': 'Lam Research Corporation',
            'PANW': 'Palo Alto Networks Inc.',
            'MU': 'Micron Technology Inc.',
            'PYPL': 'PayPal Holdings Inc.',
            'SNPS': 'Synopsys Inc.',
            'KLAC': 'KLA Corporation',
            'CDNS': 'Cadence Design Systems Inc.',
            'MELI': 'MercadoLibre Inc.',
            
            # ETFs and Indices
            'QLD': 'ProShares Ultra QQQ (2x Leveraged NASDAQ-100 ETF)',
            'QQQ': 'Invesco QQQ Trust (NASDAQ-100 ETF)',
            'SPY': 'SPDR S&P 500 ETF Trust',
            'DIA': 'SPDR Dow Jones Industrial Average ETF',
            'IWM': 'iShares Russell 2000 ETF',
            'VTI': 'Vanguard Total Stock Market ETF',
            'VOO': 'Vanguard S&P 500 ETF',
            
            # Sector ETFs
            'XLK': 'Technology Select Sector SPDR Fund',
            'XLF': 'Financial Select Sector SPDR Fund',
            'XLE': 'Energy Select Sector SPDR Fund',
            'XLV': 'Health Care Select Sector SPDR Fund',
            'XLY': 'Consumer Discretionary Select Sector SPDR Fund',
            'XLP': 'Consumer Staples Select Sector SPDR Fund',
            'XLI': 'Industrial Select Sector SPDR Fund',
            'XLB': 'Materials Select Sector SPDR Fund',
            'XLRE': 'Real Estate Select Sector SPDR Fund',
            'XLU': 'Utilities Select Sector SPDR Fund',
            'XLC': 'Communication Services Select Sector SPDR Fund',
            
            # Other tickers that might appear
            'BARL': 'Barclays PLC',  # May be ETF or ADR
            'AME': 'AMETEK Inc.',
            'ALB': 'Albemarle Corporation',
            'ITOT': 'iShares Core S&P Total Stock Market ETF',
        }
        
        for ticker_symbol in all_tickers:
            # Get company name from map or generate default
            company_name = company_name_map.get(
                ticker_symbol,
                f'{ticker_symbol} Corporation'  # Default fallback
            )
            
            try:
                if dry_run:
                    # Check if exists
                    exists = Ticker.objects.filter(symbol=ticker_symbol).exists()
                    if exists:
                        self.stdout.write(
                            f'  ✓ {ticker_symbol:6} - {company_name[:50]} (exists)'
                        )
                        existing_count += 1
                    else:
                        self.stdout.write(
                            f'  + {ticker_symbol:6} - {company_name[:50]} (would create)'
                        )
                        created_count += 1
                else:
                    # Create or get existing
                    ticker, created = Ticker.objects.get_or_create(
                        symbol=ticker_symbol,
                        defaults={'company_name': company_name}
                    )
                    
                    if created:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'  ✅ Created: {ticker_symbol:6} - {company_name[:50]}'
                            )
                        )
                        created_count += 1
                    else:
                        # Update company name if it changed
                        if ticker.company_name != company_name:
                            ticker.company_name = company_name
                            ticker.save()
                            self.stdout.write(
                                self.style.WARNING(
                                    f'  🔄 Updated: {ticker_symbol:6} - {company_name[:50]}'
                                )
                            )
                        else:
                            self.stdout.write(
                                f'  ✓ {ticker_symbol:6} - {company_name[:50]} (exists)'
                            )
                        existing_count += 1
                        
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'  ❌ Error with {ticker_symbol}: {e}'
                    )
                )
                skipped_count += 1
        
        # Summary
        self.stdout.write(self.style.SUCCESS(
            f'\n{"="*70}\n'
            f'📊 Summary:\n'
            f'   Total tickers processed: {len(all_tickers)}\n'
            f'   {"Would create" if dry_run else "Created"}: {created_count}\n'
            f'   Already exists: {existing_count}\n'
            f'   Errors/Skipped: {skipped_count}\n'
            f'{"="*70}\n'
        ))
        
        if dry_run:
            self.stdout.write(self.style.WARNING(
                '⚠️  DRY RUN - No changes made. Run without --dry-run to create tickers.\n'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                '✅ Ticker sync complete! All news sources should now find their tickers.\n'
            ))
            
            # Verify critical tickers
            critical_tickers = ['QLD', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA']
            missing_critical = []
            for symbol in critical_tickers:
                if not Ticker.objects.filter(symbol=symbol).exists():
                    missing_critical.append(symbol)
            
            if missing_critical:
                self.stdout.write(self.style.ERROR(
                    f'⚠️  WARNING: Critical tickers still missing: {", ".join(missing_critical)}\n'
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    '✅ All critical tickers verified!\n'
                ))

