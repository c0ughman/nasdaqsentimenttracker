"""
Delete articles that were fetched today but published outside current calendar day
"""

import os
import psycopg2
from urllib.parse import urlparse
from django.core.management.base import BaseCommand
from django.utils import timezone
from api.models import NewsArticle
from datetime import datetime, date


class Command(BaseCommand):
    help = 'Delete articles fetched today but published outside current calendar day'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )
        parser.add_argument(
            '--database',
            type=str,
            default='railway',
            help='Database: "railway" or "local" (default: railway)'
        )

    def connect_to_railway(self):
        """Connect to Railway PostgreSQL database"""
        railway_db_url = os.getenv('RAILWAY_DATABASE_URL')
        
        if not railway_db_url:
            self.stdout.write(self.style.ERROR(
                '❌ RAILWAY_DATABASE_URL not found in environment variables'
            ))
            return None
        
        try:
            parsed = urlparse(railway_db_url)
            conn = psycopg2.connect(
                database=parsed.path[1:],
                user=parsed.username,
                password=parsed.password,
                host=parsed.hostname,
                port=parsed.port
            )
            self.stdout.write(self.style.SUCCESS('✓ Connected to Railway database'))
            return conn
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Failed to connect to Railway: {e}'))
            return None

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        database = options['database']
        
        # Get current date
        today = timezone.now().date()
        
        self.stdout.write(self.style.SUCCESS(f'\n🧹 Cleaning up mismatched articles'))
        self.stdout.write(self.style.SUCCESS(f'Today: {today}'))
        self.stdout.write(self.style.SUCCESS(f'Database: {database.upper()}'))
        self.stdout.write(self.style.SUCCESS(f'Mode: {"DRY RUN" if dry_run else "DELETE"}\n'))
        
        # Connect to database
        if database == 'railway':
            conn = self.connect_to_railway()
            if not conn:
                return
            cursor = conn.cursor()
            
            # Query Railway database directly
            cursor.execute("""
                SELECT na.id, na.headline, na.published_at, na.fetched_at, t.symbol
                FROM api_newsarticle na
                LEFT JOIN api_ticker t ON na.ticker_id = t.id
                WHERE DATE(na.fetched_at) = %s
                AND DATE(na.published_at) != %s
                ORDER BY na.fetched_at DESC
            """, [today, today])
            
            rows = cursor.fetchall()
            count = len(rows)
            
            if count == 0:
                self.stdout.write(self.style.SUCCESS('✅ No mismatched articles found!'))
                conn.close()
                return
            
            self.stdout.write(self.style.WARNING(f'Found {count} articles to delete:\n'))
            
            # Show sample articles
            for i, (article_id, headline, published_at, fetched_at, symbol) in enumerate(rows[:10]):
                headline_short = (headline[:60] + '...') if headline and len(headline) > 60 else (headline or 'N/A')
                self.stdout.write(
                    f"  • [{symbol or 'N/A'}] {headline_short}\n"
                    f"    Published: {published_at.date() if published_at else 'N/A'} | "
                    f"Fetched: {fetched_at.date() if fetched_at else 'N/A'} | "
                    f"ID: {article_id}"
                )
            
            if count > 10:
                self.stdout.write(f"\n  ... and {count - 10} more articles")
            
            # Get breakdown by published date
            cursor.execute("""
                SELECT DATE(published_at) as pub_date, COUNT(*) as cnt
                FROM api_newsarticle
                WHERE DATE(fetched_at) = %s
                AND DATE(published_at) != %s
                GROUP BY DATE(published_at)
                ORDER BY pub_date
            """, [today, today])
            
            breakdown = cursor.fetchall()
            self.stdout.write(f"\n📊 Breakdown by published date:")
            for pub_date, article_count in breakdown:
                self.stdout.write(f"  {pub_date}: {article_count} articles")
            
            if dry_run:
                self.stdout.write(self.style.WARNING(f'\n⚠️  DRY RUN: Would delete {count} articles'))
                self.stdout.write(self.style.WARNING('Run without --dry-run to actually delete'))
            else:
                # Confirm deletion
                self.stdout.write(self.style.ERROR(f'\n⚠️  About to DELETE {count} articles'))
                response = input('Type "DELETE" to confirm: ')
                
                if response == 'DELETE':
                    # Delete articles
                    cursor.execute("""
                        DELETE FROM api_newsarticle
                        WHERE DATE(fetched_at) = %s
                        AND DATE(published_at) != %s
                    """, [today, today])
                    
                    deleted_count = cursor.rowcount
                    conn.commit()
                    
                    self.stdout.write(self.style.SUCCESS(f'\n✅ Deleted {deleted_count} articles'))
                else:
                    self.stdout.write(self.style.ERROR('\n❌ Deletion cancelled'))
            
            conn.close()
        else:
            # Use local Django ORM
            mismatched_articles = NewsArticle.objects.filter(
                fetched_at__date=today,  # Fetched today
            ).exclude(
                published_at__date=today  # But NOT published today
            ).select_related('ticker')
            
            count = mismatched_articles.count()
            
            if count == 0:
                self.stdout.write(self.style.SUCCESS('✅ No mismatched articles found!'))
                return
            
            self.stdout.write(self.style.WARNING(f'Found {count} articles to delete:\n'))
            
            # Show sample articles
            sample_articles = mismatched_articles[:10]
            for article in sample_articles:
                self.stdout.write(
                    f"  • [{article.ticker.symbol if article.ticker else 'N/A'}] "
                    f"{article.headline[:60]}...\n"
                    f"    Published: {article.published_at.date()} | "
                    f"Fetched: {article.fetched_at.date()}"
                )
            
            if count > 10:
                self.stdout.write(f"\n  ... and {count - 10} more articles")
            
            # Group by published date for summary
            from collections import defaultdict
            by_published_date = defaultdict(int)
            for article in mismatched_articles:
                pub_date = article.published_at.date()
                by_published_date[pub_date] += 1
            
            self.stdout.write(f"\n📊 Breakdown by published date:")
            for pub_date, article_count in sorted(by_published_date.items()):
                self.stdout.write(f"  {pub_date}: {article_count} articles")
            
            if dry_run:
                self.stdout.write(self.style.WARNING(f'\n⚠️  DRY RUN: Would delete {count} articles'))
                self.stdout.write(self.style.WARNING('Run without --dry-run to actually delete'))
            else:
                # Confirm deletion
                self.stdout.write(self.style.ERROR(f'\n⚠️  About to DELETE {count} articles'))
                response = input('Type "DELETE" to confirm: ')
                
                if response == 'DELETE':
                    # Delete articles
                    deleted_count = 0
                    for article in mismatched_articles:
                        article.delete()
                        deleted_count += 1
                    
                    self.stdout.write(self.style.SUCCESS(f'\n✅ Deleted {deleted_count} articles'))
                else:
                    self.stdout.write(self.style.ERROR('\n❌ Deletion cancelled'))

