"""
Extract today's SecondSnapshot and AnalysisRun data from Railway database
Exports to CSV and JSON for analysis and charting
"""

import os
import json
import csv
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import connection
from api.models import SecondSnapshot, AnalysisRun, Ticker
import psycopg2
from urllib.parse import urlparse


class Command(BaseCommand):
    help = 'Extract today\'s SecondSnapshot and AnalysisRun data from Railway database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--database',
            type=str,
            default='railway',
            help='Database to extract from: "railway" or "local" (default: railway)'
        )
        parser.add_argument(
            '--date',
            type=str,
            help='Date to extract (YYYY-MM-DD). Default: today'
        )
        parser.add_argument(
            '--output-dir',
            type=str,
            default='./data_exports',
            help='Output directory for exported files (default: ./data_exports)'
        )
        parser.add_argument(
            '--format',
            type=str,
            default='both',
            help='Output format: "csv", "json", or "both" (default: both)'
        )

    def handle(self, *args, **options):
        database = options['database']
        output_dir = options['output_dir']
        output_format = options['format']

        # Parse date
        if options['date']:
            try:
                target_date = datetime.strptime(options['date'], '%Y-%m-%d').date()
            except ValueError:
                self.stdout.write(self.style.ERROR('Invalid date format. Use YYYY-MM-DD'))
                return
        else:
            target_date = timezone.now().date()

        self.stdout.write(self.style.SUCCESS(f'\n📊 Extracting data for {target_date}'))
        self.stdout.write(self.style.SUCCESS(f'Database: {database.upper()}'))
        self.stdout.write(self.style.SUCCESS(f'Output directory: {output_dir}\n'))

        # Create output directory
        os.makedirs(output_dir, exist_ok=True)

        # Connect to database
        if database == 'railway':
            conn = self.connect_to_railway()
            if not conn:
                return
        else:
            conn = connection

        try:
            # Extract SecondSnapshot data
            self.stdout.write('Extracting SecondSnapshot data...')
            second_snapshots = self.extract_second_snapshots(conn, target_date, database)

            # Extract AnalysisRun data
            self.stdout.write('Extracting AnalysisRun data...')
            analysis_runs = self.extract_analysis_runs(conn, target_date, database)

            # Export data
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

            if output_format in ['csv', 'both']:
                self.export_to_csv(second_snapshots, analysis_runs, output_dir, target_date, timestamp)

            if output_format in ['json', 'both']:
                self.export_to_json(second_snapshots, analysis_runs, output_dir, target_date, timestamp)

            # Print summary statistics
            self.print_summary(second_snapshots, analysis_runs, target_date)

        finally:
            if database == 'railway' and conn:
                conn.close()

    def connect_to_railway(self):
        """Connect to Railway PostgreSQL database"""
        # Railway database URL format:
        # postgresql://postgres:password@host:port/railway
        railway_db_url = os.getenv('RAILWAY_DATABASE_URL')

        if not railway_db_url:
            self.stdout.write(self.style.ERROR(
                '❌ RAILWAY_DATABASE_URL not found in environment variables'
            ))
            self.stdout.write(self.style.WARNING(
                '\nPlease add your Railway database URL to .env:\n'
                'RAILWAY_DATABASE_URL=postgresql://postgres:xxxxx@xxx.railway.app:5432/railway'
            ))
            return None

        try:
            self.stdout.write('Connecting to Railway database...')
            url = urlparse(railway_db_url)

            conn = psycopg2.connect(
                database=url.path[1:],
                user=url.username,
                password=url.password,
                host=url.hostname,
                port=url.port
            )

            self.stdout.write(self.style.SUCCESS('✓ Connected to Railway database'))
            return conn

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Failed to connect to Railway: {str(e)}'))
            return None

    def extract_second_snapshots(self, conn, target_date, database):
        """Extract SecondSnapshot data for the target date"""
        start_datetime = timezone.make_aware(datetime.combine(target_date, datetime.min.time()))
        end_datetime = timezone.make_aware(datetime.combine(target_date, datetime.max.time()))

        if database == 'railway':
            # Raw SQL query for Railway
            cursor = conn.cursor()
            query = """
                SELECT
                    ss.id,
                    t.symbol as ticker_symbol,
                    ss.timestamp,
                    ss.ohlc_1sec_open,
                    ss.ohlc_1sec_high,
                    ss.ohlc_1sec_low,
                    ss.ohlc_1sec_close,
                    ss.ohlc_1sec_volume,
                    ss.ohlc_1sec_tick_count,
                    ss.composite_score,
                    ss.news_score_cached,
                    ss.technical_score_cached,
                    ss.source,
                    ss.created_at
                FROM api_second_snapshot ss
                JOIN api_ticker t ON ss.ticker_id = t.id
                WHERE ss.timestamp >= %s AND ss.timestamp <= %s
                ORDER BY ss.timestamp ASC
            """
            cursor.execute(query, [start_datetime, end_datetime])

            columns = [desc[0] for desc in cursor.description]
            data = []
            for row in cursor.fetchall():
                data.append(dict(zip(columns, row)))

            cursor.close()
            return data
        else:
            # Django ORM for local
            snapshots = SecondSnapshot.objects.filter(
                timestamp__gte=start_datetime,
                timestamp__lte=end_datetime
            ).select_related('ticker').order_by('timestamp')

            return [
                {
                    'id': snap.id,
                    'ticker_symbol': snap.ticker.symbol,
                    'timestamp': snap.timestamp,
                    'ohlc_1sec_open': float(snap.ohlc_1sec_open),
                    'ohlc_1sec_high': float(snap.ohlc_1sec_high),
                    'ohlc_1sec_low': float(snap.ohlc_1sec_low),
                    'ohlc_1sec_close': float(snap.ohlc_1sec_close),
                    'ohlc_1sec_volume': snap.ohlc_1sec_volume,
                    'ohlc_1sec_tick_count': snap.ohlc_1sec_tick_count,
                    'composite_score': snap.composite_score,
                    'news_score_cached': snap.news_score_cached,
                    'technical_score_cached': snap.technical_score_cached,
                    'source': snap.source,
                    'created_at': snap.created_at,
                }
                for snap in snapshots
            ]

    def extract_analysis_runs(self, conn, target_date, database):
        """Extract AnalysisRun data for the target date"""
        start_datetime = timezone.make_aware(datetime.combine(target_date, datetime.min.time()))
        end_datetime = timezone.make_aware(datetime.combine(target_date, datetime.max.time()))

        if database == 'railway':
            # Raw SQL query for Railway
            cursor = conn.cursor()
            query = """
                SELECT
                    ar.id,
                    t.symbol as ticker_symbol,
                    ar.timestamp,
                    ar.composite_score,
                    ar.sentiment_label,
                    ar.avg_base_sentiment,
                    ar.avg_surprise_factor,
                    ar.avg_novelty,
                    ar.avg_source_credibility,
                    ar.avg_recency_weight,
                    ar.stock_price,
                    ar.price_open,
                    ar.price_high,
                    ar.price_low,
                    ar.price_change_percent,
                    ar.volume,
                    ar.articles_analyzed,
                    ar.cached_articles,
                    ar.new_articles,
                    ar.rsi_14,
                    ar.macd,
                    ar.macd_signal,
                    ar.macd_histogram,
                    ar.technical_composite_score,
                    ar.reddit_sentiment,
                    ar.reddit_posts_analyzed,
                    ar.analyst_recommendations_score
                FROM api_analysisrun ar
                JOIN api_ticker t ON ar.ticker_id = t.id
                WHERE ar.timestamp >= %s AND ar.timestamp <= %s
                ORDER BY ar.timestamp ASC
            """
            cursor.execute(query, [start_datetime, end_datetime])

            columns = [desc[0] for desc in cursor.description]
            data = []
            for row in cursor.fetchall():
                data.append(dict(zip(columns, row)))

            cursor.close()
            return data
        else:
            # Django ORM for local
            runs = AnalysisRun.objects.filter(
                timestamp__gte=start_datetime,
                timestamp__lte=end_datetime
            ).select_related('ticker').order_by('timestamp')

            return [
                {
                    'id': run.id,
                    'ticker_symbol': run.ticker.symbol,
                    'timestamp': run.timestamp,
                    'composite_score': run.composite_score,
                    'sentiment_label': run.sentiment_label,
                    'avg_base_sentiment': run.avg_base_sentiment,
                    'avg_surprise_factor': run.avg_surprise_factor,
                    'avg_novelty': run.avg_novelty,
                    'avg_source_credibility': run.avg_source_credibility,
                    'avg_recency_weight': run.avg_recency_weight,
                    'stock_price': float(run.stock_price),
                    'price_open': float(run.price_open) if run.price_open else None,
                    'price_high': float(run.price_high) if run.price_high else None,
                    'price_low': float(run.price_low) if run.price_low else None,
                    'price_change_percent': run.price_change_percent,
                    'volume': run.volume,
                    'articles_analyzed': run.articles_analyzed,
                    'cached_articles': run.cached_articles,
                    'new_articles': run.new_articles,
                    'rsi_14': run.rsi_14,
                    'macd': run.macd,
                    'macd_signal': run.macd_signal,
                    'macd_histogram': run.macd_histogram,
                    'technical_composite_score': run.technical_composite_score,
                    'reddit_sentiment': run.reddit_sentiment,
                    'reddit_posts_analyzed': run.reddit_posts_analyzed,
                    'analyst_recommendations_score': run.analyst_recommendations_score,
                }
                for run in runs
            ]

    def export_to_csv(self, second_snapshots, analysis_runs, output_dir, target_date, timestamp):
        """Export data to CSV files"""
        date_str = target_date.strftime('%Y%m%d')

        # Export SecondSnapshots
        if second_snapshots:
            filename = f'{output_dir}/second_snapshots_{date_str}_{timestamp}.csv'
            with open(filename, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=second_snapshots[0].keys())
                writer.writeheader()
                writer.writerows(second_snapshots)
            self.stdout.write(self.style.SUCCESS(f'✓ Exported SecondSnapshots to {filename}'))

        # Export AnalysisRuns
        if analysis_runs:
            filename = f'{output_dir}/analysis_runs_{date_str}_{timestamp}.csv'
            with open(filename, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=analysis_runs[0].keys())
                writer.writeheader()
                writer.writerows(analysis_runs)
            self.stdout.write(self.style.SUCCESS(f'✓ Exported AnalysisRuns to {filename}'))

    def export_to_json(self, second_snapshots, analysis_runs, output_dir, target_date, timestamp):
        """Export data to JSON files"""
        date_str = target_date.strftime('%Y%m%d')

        # Helper to serialize datetime and decimal objects
        def json_serial(obj):
            from decimal import Decimal
            if isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, Decimal):
                return float(obj)
            raise TypeError(f'Type {type(obj)} not serializable')

        # Export SecondSnapshots
        if second_snapshots:
            filename = f'{output_dir}/second_snapshots_{date_str}_{timestamp}.json'
            with open(filename, 'w') as f:
                json.dump(second_snapshots, f, indent=2, default=json_serial)
            self.stdout.write(self.style.SUCCESS(f'✓ Exported SecondSnapshots to {filename}'))

        # Export AnalysisRuns
        if analysis_runs:
            filename = f'{output_dir}/analysis_runs_{date_str}_{timestamp}.json'
            with open(filename, 'w') as f:
                json.dump(analysis_runs, f, indent=2, default=json_serial)
            self.stdout.write(self.style.SUCCESS(f'✓ Exported AnalysisRuns to {filename}'))

    def print_summary(self, second_snapshots, analysis_runs, target_date):
        """Print summary statistics"""
        self.stdout.write(self.style.SUCCESS(f'\n{"="*60}'))
        self.stdout.write(self.style.SUCCESS(f'📊 DATA EXTRACTION SUMMARY - {target_date}'))
        self.stdout.write(self.style.SUCCESS(f'{"="*60}\n'))

        # SecondSnapshots summary
        self.stdout.write(self.style.SUCCESS('📈 SECOND SNAPSHOTS:'))
        self.stdout.write(f'  Total records: {len(second_snapshots)}')

        if second_snapshots:
            tickers = set(s['ticker_symbol'] for s in second_snapshots)
            self.stdout.write(f'  Tickers: {", ".join(sorted(tickers))}')

            first_ts = second_snapshots[0]['timestamp']
            last_ts = second_snapshots[-1]['timestamp']
            self.stdout.write(f'  Time range: {first_ts} to {last_ts}')

            # Composite scores
            scores = [s['composite_score'] for s in second_snapshots if s['composite_score'] is not None]
            if scores:
                self.stdout.write(f'  Composite score range: {min(scores):.2f} to {max(scores):.2f}')
                self.stdout.write(f'  Composite score avg: {sum(scores)/len(scores):.2f}')

        self.stdout.write('')

        # AnalysisRuns summary
        self.stdout.write(self.style.SUCCESS('📰 ANALYSIS RUNS:'))
        self.stdout.write(f'  Total records: {len(analysis_runs)}')

        if analysis_runs:
            tickers = set(r['ticker_symbol'] for r in analysis_runs)
            self.stdout.write(f'  Tickers: {", ".join(sorted(tickers))}')

            first_ts = analysis_runs[0]['timestamp']
            last_ts = analysis_runs[-1]['timestamp']
            self.stdout.write(f'  Time range: {first_ts} to {last_ts}')

            # Composite scores
            scores = [r['composite_score'] for r in analysis_runs]
            self.stdout.write(f'  Composite score range: {min(scores):.2f} to {max(scores):.2f}')
            self.stdout.write(f'  Composite score avg: {sum(scores)/len(scores):.2f}')

            # Articles
            total_articles = sum(r['articles_analyzed'] for r in analysis_runs)
            self.stdout.write(f'  Total articles analyzed: {total_articles}')

        self.stdout.write(self.style.SUCCESS(f'\n{"="*60}\n'))
