"""
Data Cleanup Management Command

Automatically removes old data based on retention policies:
- OHLCVTick: 1 hour (raw tick data)
- SecondSnapshot: 48 hours (1-second candles)
- TickCandle100: 48 hours (100-tick candles)
- Everything else: 7 days (AnalysisRun, NewsArticle, Reddit data)

Run with: python manage.py cleanup_old_data
Options:
  --dry-run: Show what would be deleted without actually deleting
  --verbose: Show detailed deletion information
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from api.models import (
    OHLCVTick,
    SecondSnapshot,
    TickCandle100,
    AnalysisRun,
    NewsArticle,
    RedditPost,
    RedditComment,
    RedditAnalysisRun,
    SentimentHistory,
    TickerContribution
)


class Command(BaseCommand):
    help = 'Clean up old data based on retention policies'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed deletion information'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verbose = options['verbose']

        self.stdout.write(self.style.SUCCESS(
            '\n' + '='*70 + '\n'
            '🧹 Data Cleanup - Starting\n'
            '='*70
        ))

        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No data will be deleted\n'))

        total_deleted = 0

        # ====================================================================
        # 1. OHLCVTick - Keep only 1 hour
        # ====================================================================
        cutoff_1h = timezone.now() - timedelta(hours=1)

        if verbose or dry_run:
            count = OHLCVTick.objects.filter(timestamp__lt=cutoff_1h).count()
            self.stdout.write(
                f'📊 OHLCVTick (raw ticks): {count:,} records older than 1 hour'
            )

        if not dry_run:
            deleted = OHLCVTick.objects.filter(timestamp__lt=cutoff_1h).delete()
            total_deleted += deleted[0]
            self.stdout.write(self.style.SUCCESS(
                f'   ✅ Deleted {deleted[0]:,} OHLCVTick records'
            ))

        # ====================================================================
        # 2. SecondSnapshot - Keep 48 hours
        # ====================================================================
        cutoff_48h = timezone.now() - timedelta(hours=48)

        if verbose or dry_run:
            count = SecondSnapshot.objects.filter(timestamp__lt=cutoff_48h).count()
            self.stdout.write(
                f'📊 SecondSnapshot (1-second candles): {count:,} records older than 48 hours'
            )

        if not dry_run:
            deleted = SecondSnapshot.objects.filter(timestamp__lt=cutoff_48h).delete()
            total_deleted += deleted[0]
            self.stdout.write(self.style.SUCCESS(
                f'   ✅ Deleted {deleted[0]:,} SecondSnapshot records'
            ))

        # ====================================================================
        # 3. TickCandle100 - Keep 48 hours
        # ====================================================================
        if verbose or dry_run:
            count = TickCandle100.objects.filter(completed_at__lt=cutoff_48h).count()
            self.stdout.write(
                f'📊 TickCandle100 (100-tick candles): {count:,} records older than 48 hours'
            )

        if not dry_run:
            deleted = TickCandle100.objects.filter(completed_at__lt=cutoff_48h).delete()
            total_deleted += deleted[0]
            self.stdout.write(self.style.SUCCESS(
                f'   ✅ Deleted {deleted[0]:,} TickCandle100 records'
            ))

        # ====================================================================
        # 4. Everything else - Keep 7 days
        # ====================================================================
        cutoff_7d = timezone.now() - timedelta(days=7)

        # AnalysisRun
        if verbose or dry_run:
            count = AnalysisRun.objects.filter(timestamp__lt=cutoff_7d).count()
            self.stdout.write(
                f'📊 AnalysisRun: {count:,} records older than 7 days'
            )

        if not dry_run:
            deleted = AnalysisRun.objects.filter(timestamp__lt=cutoff_7d).delete()
            total_deleted += deleted[0]
            self.stdout.write(self.style.SUCCESS(
                f'   ✅ Deleted {deleted[0]:,} AnalysisRun records'
            ))

        # NewsArticle
        if verbose or dry_run:
            count = NewsArticle.objects.filter(published_at__lt=cutoff_7d).count()
            self.stdout.write(
                f'📊 NewsArticle: {count:,} records older than 7 days'
            )

        if not dry_run:
            deleted = NewsArticle.objects.filter(published_at__lt=cutoff_7d).delete()
            total_deleted += deleted[0]
            self.stdout.write(self.style.SUCCESS(
                f'   ✅ Deleted {deleted[0]:,} NewsArticle records'
            ))

        # RedditPost
        if verbose or dry_run:
            count = RedditPost.objects.filter(created_utc__lt=cutoff_7d).count()
            self.stdout.write(
                f'📊 RedditPost: {count:,} records older than 7 days'
            )

        if not dry_run:
            deleted = RedditPost.objects.filter(created_utc__lt=cutoff_7d).delete()
            total_deleted += deleted[0]
            self.stdout.write(self.style.SUCCESS(
                f'   ✅ Deleted {deleted[0]:,} RedditPost records'
            ))

        # RedditComment (cascade deletes with RedditPost, but clean orphans)
        if verbose or dry_run:
            count = RedditComment.objects.filter(created_utc__lt=cutoff_7d).count()
            self.stdout.write(
                f'📊 RedditComment: {count:,} records older than 7 days'
            )

        if not dry_run:
            deleted = RedditComment.objects.filter(created_utc__lt=cutoff_7d).delete()
            total_deleted += deleted[0]
            self.stdout.write(self.style.SUCCESS(
                f'   ✅ Deleted {deleted[0]:,} RedditComment records'
            ))

        # RedditAnalysisRun
        if verbose or dry_run:
            count = RedditAnalysisRun.objects.filter(timestamp__lt=cutoff_7d).count()
            self.stdout.write(
                f'📊 RedditAnalysisRun: {count:,} records older than 7 days'
            )

        if not dry_run:
            deleted = RedditAnalysisRun.objects.filter(timestamp__lt=cutoff_7d).delete()
            total_deleted += deleted[0]
            self.stdout.write(self.style.SUCCESS(
                f'   ✅ Deleted {deleted[0]:,} RedditAnalysisRun records'
            ))

        # TickerContribution (linked to AnalysisRun, will cascade, but clean orphans)
        if verbose or dry_run:
            count = TickerContribution.objects.filter(created_at__lt=cutoff_7d).count()
            self.stdout.write(
                f'📊 TickerContribution: {count:,} records older than 7 days'
            )

        if not dry_run:
            deleted = TickerContribution.objects.filter(created_at__lt=cutoff_7d).delete()
            total_deleted += deleted[0]
            self.stdout.write(self.style.SUCCESS(
                f'   ✅ Deleted {deleted[0]:,} TickerContribution records'
            ))

        # SentimentHistory - Keep longer for historical trending (30 days)
        cutoff_30d = timezone.now() - timedelta(days=30)

        if verbose or dry_run:
            count = SentimentHistory.objects.filter(date__lt=cutoff_30d.date()).count()
            self.stdout.write(
                f'📊 SentimentHistory: {count:,} records older than 30 days'
            )

        if not dry_run:
            deleted = SentimentHistory.objects.filter(date__lt=cutoff_30d.date()).delete()
            total_deleted += deleted[0]
            self.stdout.write(self.style.SUCCESS(
                f'   ✅ Deleted {deleted[0]:,} SentimentHistory records'
            ))

        # ====================================================================
        # Summary
        # ====================================================================
        self.stdout.write(self.style.SUCCESS(
            '\n' + '='*70 + '\n'
            f'🎉 Cleanup Complete\n'
            '='*70
        ))

        if dry_run:
            self.stdout.write(self.style.WARNING(
                '🔍 DRY RUN - No data was actually deleted'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'✅ Total records deleted: {total_deleted:,}'
            ))

        self.stdout.write('\n📋 Retention Policy Applied:')
        self.stdout.write('   • OHLCVTick: 1 hour')
        self.stdout.write('   • SecondSnapshot: 48 hours')
        self.stdout.write('   • TickCandle100: 48 hours')
        self.stdout.write('   • AnalysisRun: 7 days')
        self.stdout.write('   • NewsArticle: 7 days')
        self.stdout.write('   • Reddit data: 7 days')
        self.stdout.write('   • SentimentHistory: 30 days')
        self.stdout.write('')
