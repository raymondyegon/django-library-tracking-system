"""
Django management command to populate the database with realistic test data.

Usage:
    python manage.py seed_data          # Seeds all data (idempotent — safe to run multiple times)
    python manage.py seed_data --flush  # Clears existing data first, then seeds fresh

What it creates:
    - 1 superuser (admin/admin123)
    - 8 regular users with Member profiles
    - 6 authors spanning different literary traditions
    - 15 books across various genres
    - 20 loans with a mix of:
        * Active loans (not returned, due in the future)
        * Overdue loans (not returned, due date in the past) — for testing check_overdue_loans task
        * Returned loans (is_returned=True, return_date set)

This gives you data to test every feature:
    - Pagination: 15 books across 2 pages (at page_size=10)
    - select_related optimization: books with nested author data
    - Overdue notifications: overdue loans trigger the Celery task
    - extend_due_date: active (non-overdue) loans can be extended
    - top-active members: members with varying active loan counts
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone

from library.models import Author, Book, Member, Loan


class Command(BaseCommand):
    help = "Seed the database with test data for the Library Tracking System"

    def add_arguments(self, parser):
        # Optional flag to wipe existing data before seeding
        parser.add_argument(
            '--flush',
            action='store_true',
            help='Delete all existing library data before seeding',
        )

    def handle(self, *args, **options):
        if options['flush']:
            self.stdout.write("Flushing existing library data...")
            Loan.objects.all().delete()
            Book.objects.all().delete()
            Author.objects.all().delete()
            Member.objects.all().delete()
            # Delete non-superuser accounts created by previous seeds
            User.objects.filter(is_superuser=False).delete()
            self.stdout.write(self.style.WARNING("All library data cleared."))

        self._create_superuser()
        users = self._create_users()
        members = self._create_members(users)
        authors = self._create_authors()
        books = self._create_books(authors)
        self._create_loans(members, books)

        self.stdout.write(self.style.SUCCESS("Database seeded successfully!"))

    # ──────────────────────────────────────────────
    # Superuser
    # ──────────────────────────────────────────────

    def _create_superuser(self):
        """Create an admin superuser for accessing /admin panel."""
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser(
                username='admin',
                email='admin@library.com',
                password='admin123',
            )
            self.stdout.write("  Created superuser: admin / admin123")
        else:
            self.stdout.write("  Superuser 'admin' already exists — skipping.")

    # ──────────────────────────────────────────────
    # Users
    # ──────────────────────────────────────────────

    def _create_users(self):
        """Create 8 regular users that will become library members."""
        user_data = [
            {'username': 'john_doe', 'email': 'john@example.com', 'first_name': 'John', 'last_name': 'Doe'},
            {'username': 'jane_doe', 'email': 'jane@example.com', 'first_name': 'Jane', 'last_name': 'Doe'},
            {'username': 'alice_smith', 'email': 'alice@example.com', 'first_name': 'Alice', 'last_name': 'Smith'},
            {'username': 'bob_jones', 'email': 'bob@example.com', 'first_name': 'Bob', 'last_name': 'Jones'},
            {'username': 'carol_white', 'email': 'carol@example.com', 'first_name': 'Carol', 'last_name': 'White'},
            {'username': 'dave_brown', 'email': 'dave@example.com', 'first_name': 'Dave', 'last_name': 'Brown'},
            {'username': 'eve_wilson', 'email': 'eve@example.com', 'first_name': 'Eve', 'last_name': 'Wilson'},
            {'username': 'frank_lee', 'email': 'frank@example.com', 'first_name': 'Frank', 'last_name': 'Lee'},
        ]

        users = []
        for data in user_data:
            user, created = User.objects.get_or_create(
                username=data['username'],
                defaults={
                    'email': data['email'],
                    'first_name': data['first_name'],
                    'last_name': data['last_name'],
                },
            )
            if created:
                user.set_password('testpass123')  # All test users share the same password
                user.save()
                self.stdout.write(f"  Created user: {user.username}")
            users.append(user)

        return users

    # ──────────────────────────────────────────────
    # Members
    # ──────────────────────────────────────────────

    def _create_members(self, users):
        """Create a Member profile for each user (one-to-one relationship)."""
        members = []
        for user in users:
            member, created = Member.objects.get_or_create(user=user)
            if created:
                self.stdout.write(f"  Created member: {user.username}")
            members.append(member)
        return members

    # ──────────────────────────────────────────────
    # Authors
    # ──────────────────────────────────────────────

    def _create_authors(self):
        """Create 6 authors with short biographies."""
        author_data = [
            {
                'first_name': 'George',
                'last_name': 'Orwell',
                'biography': 'English novelist known for his sharp criticism of political oppression.',
            },
            {
                'first_name': 'Jane',
                'last_name': 'Austen',
                'biography': 'English novelist known for her witty social commentary and romance.',
            },
            {
                'first_name': 'Isaac',
                'last_name': 'Asimov',
                'biography': 'American author and professor, prolific writer of science fiction.',
            },
            {
                'first_name': 'Chimamanda',
                'last_name': 'Adichie',
                'biography': 'Nigerian author whose works range from novels to feminist essays.',
            },
            {
                'first_name': 'Walter',
                'last_name': 'Isaacson',
                'biography': 'American journalist and biographer of Steve Jobs and Albert Einstein.',
            },
            {
                'first_name': 'Toni',
                'last_name': 'Morrison',
                'biography': 'Nobel Prize-winning American novelist known for her powerful narratives.',
            },
        ]

        authors = []
        for data in author_data:
            author, created = Author.objects.get_or_create(
                first_name=data['first_name'],
                last_name=data['last_name'],
                defaults={'biography': data['biography']},
            )
            if created:
                self.stdout.write(f"  Created author: {author}")
            authors.append(author)

        return authors

    # ──────────────────────────────────────────────
    # Books
    # ──────────────────────────────────────────────

    def _create_books(self, authors):
        """
        Create 15 books across different genres.
        Each book is linked to one of the seeded authors.
        available_copies varies so some books can become unavailable after loaning.
        """
        # Unpack authors by index for readability
        orwell, austen, asimov, adichie, isaacson, morrison = authors

        book_data = [
            # Fiction
            {'title': '1984', 'author': orwell, 'isbn': '9780451524935', 'genre': 'fiction', 'available_copies': 3},
            {'title': 'Animal Farm', 'author': orwell, 'isbn': '9780451526342', 'genre': 'fiction', 'available_copies': 2},
            {'title': 'Pride and Prejudice', 'author': austen, 'isbn': '9780141439518', 'genre': 'fiction', 'available_copies': 4},
            {'title': 'Sense and Sensibility', 'author': austen, 'isbn': '9780141439662', 'genre': 'fiction', 'available_copies': 2},
            {'title': 'Emma', 'author': austen, 'isbn': '9780141439587', 'genre': 'fiction', 'available_copies': 1},
            {'title': 'Beloved', 'author': morrison, 'isbn': '9781400033416', 'genre': 'fiction', 'available_copies': 3},
            {'title': 'Song of Solomon', 'author': morrison, 'isbn': '9781400033423', 'genre': 'fiction', 'available_copies': 2},

            # Non-Fiction
            {'title': 'Half of a Yellow Sun', 'author': adichie, 'isbn': '9781400095209', 'genre': 'nonfiction', 'available_copies': 3},
            {'title': 'Americanah', 'author': adichie, 'isbn': '9780307455925', 'genre': 'nonfiction', 'available_copies': 2},

            # Sci-Fi
            {'title': 'Foundation', 'author': asimov, 'isbn': '9780553293357', 'genre': 'sci-fi', 'available_copies': 5},
            {'title': 'I, Robot', 'author': asimov, 'isbn': '9780553294385', 'genre': 'sci-fi', 'available_copies': 3},
            {'title': 'The End of Eternity', 'author': asimov, 'isbn': '9780765319197', 'genre': 'sci-fi', 'available_copies': 2},

            # Biography
            {'title': 'Steve Jobs', 'author': isaacson, 'isbn': '9781451648539', 'genre': 'biography', 'available_copies': 4},
            {'title': 'Einstein: His Life and Universe', 'author': isaacson, 'isbn': '9780743264747', 'genre': 'biography', 'available_copies': 3},
            {'title': 'The Innovators', 'author': isaacson, 'isbn': '9781476708706', 'genre': 'biography', 'available_copies': 2},
        ]

        books = []
        for data in book_data:
            book, created = Book.objects.get_or_create(
                isbn=data['isbn'],
                defaults={
                    'title': data['title'],
                    'author': data['author'],
                    'genre': data['genre'],
                    'available_copies': data['available_copies'],
                },
            )
            if created:
                self.stdout.write(f"  Created book: {book.title} by {book.author}")
            books.append(book)

        return books

    # ──────────────────────────────────────────────
    # Loans
    # ──────────────────────────────────────────────

    def _create_loans(self, members, books):
        """
        Create a diverse set of loans for testing all features:

        - ACTIVE loans: not returned, due_date in the future
          → test extend_due_date endpoint, shows in top-active members
        - OVERDUE loans: not returned, due_date in the past
          → test check_overdue_loans Celery task, can NOT be extended
        - RETURNED loans: is_returned=True, return_date set
          → should NOT appear in overdue checks or active counts

        We also decrement available_copies for active/overdue loans to keep
        the data consistent with how the loan endpoint works.
        """
        today = timezone.now().date()

        # Skip loan creation if loans already exist (idempotent)
        if Loan.objects.exists():
            self.stdout.write("  Loans already exist — skipping loan creation.")
            return

        # ── Active loans (due in the future) ──
        # These members will appear in /api/members/top-active/
        active_loans = [
            # john_doe: 3 active loans → should be #1 in top-active
            {'member': members[0], 'book': books[0], 'days_ago': 5, 'due_in': 9},    # 1984
            {'member': members[0], 'book': books[9], 'days_ago': 3, 'due_in': 11},   # Foundation
            {'member': members[0], 'book': books[12], 'days_ago': 2, 'due_in': 12},  # Steve Jobs

            # jane_doe: 2 active loans → #2 in top-active
            {'member': members[1], 'book': books[2], 'days_ago': 7, 'due_in': 7},    # Pride and Prejudice
            {'member': members[1], 'book': books[5], 'days_ago': 4, 'due_in': 10},   # Beloved

            # alice_smith: 2 active loans → #3 in top-active (tied with jane)
            {'member': members[2], 'book': books[10], 'days_ago': 6, 'due_in': 8},   # I, Robot
            {'member': members[2], 'book': books[13], 'days_ago': 1, 'due_in': 13},  # Einstein

            # bob_jones: 1 active loan → #4 in top-active
            {'member': members[3], 'book': books[7], 'days_ago': 10, 'due_in': 4},   # Half of a Yellow Sun

            # carol_white: 1 active loan → #5 in top-active
            {'member': members[4], 'book': books[14], 'days_ago': 3, 'due_in': 11},  # The Innovators
        ]

        for data in active_loans:
            loan_date = today - timedelta(days=data['days_ago'])
            due_date = today + timedelta(days=data['due_in'])
            Loan.objects.create(
                book=data['book'],
                member=data['member'],
                due_date=due_date,
                is_returned=False,
            )
            # Decrement available copies to stay consistent
            data['book'].available_copies -= 1
            data['book'].save()

        self.stdout.write(f"  Created {len(active_loans)} active loans")

        # ── Overdue loans (due date in the past, NOT returned) ──
        # The check_overdue_loans Celery task should pick these up and send emails.
        overdue_loans = [
            # dave_brown: 2 overdue loans → will get 2 overdue emails
            {'member': members[5], 'book': books[1], 'days_ago': 20, 'overdue_by': 6},   # Animal Farm
            {'member': members[5], 'book': books[3], 'days_ago': 18, 'overdue_by': 4},   # Sense and Sensibility

            # eve_wilson: 1 overdue loan
            {'member': members[6], 'book': books[4], 'days_ago': 21, 'overdue_by': 7},   # Emma

            # frank_lee: 1 overdue loan
            {'member': members[7], 'book': books[11], 'days_ago': 25, 'overdue_by': 11}, # The End of Eternity
        ]

        for data in overdue_loans:
            loan_date = today - timedelta(days=data['days_ago'])
            due_date = today - timedelta(days=data['overdue_by'])
            Loan.objects.create(
                book=data['book'],
                member=data['member'],
                due_date=due_date,
                is_returned=False,
            )
            data['book'].available_copies -= 1
            data['book'].save()

        self.stdout.write(f"  Created {len(overdue_loans)} overdue loans")

        # ── Returned loans (historical, is_returned=True) ──
        # These should NOT count in top-active or overdue checks.
        returned_loans = [
            # john_doe returned a book in the past
            {'member': members[0], 'book': books[6], 'days_ago': 30, 'returned_ago': 16},  # Song of Solomon

            # alice_smith returned two books
            {'member': members[2], 'book': books[8], 'days_ago': 25, 'returned_ago': 12},  # Americanah
            {'member': members[2], 'book': books[12], 'days_ago': 40, 'returned_ago': 28}, # Steve Jobs (borrowed & returned before)

            # bob_jones returned a book
            {'member': members[3], 'book': books[0], 'days_ago': 35, 'returned_ago': 20},  # 1984

            # eve_wilson returned a book
            {'member': members[6], 'book': books[9], 'days_ago': 20, 'returned_ago': 8},   # Foundation

            # frank_lee returned two books
            {'member': members[7], 'book': books[2], 'days_ago': 45, 'returned_ago': 30},  # Pride and Prejudice
            {'member': members[7], 'book': books[5], 'days_ago': 50, 'returned_ago': 38},  # Beloved
        ]

        for data in returned_loans:
            loan_date = today - timedelta(days=data['days_ago'])
            return_date = today - timedelta(days=data['returned_ago'])
            due_date = loan_date + timedelta(days=14)  # Standard 14-day due date
            Loan.objects.create(
                book=data['book'],
                member=data['member'],
                due_date=due_date,
                return_date=return_date,
                is_returned=True,
            )
            # No need to decrement available_copies — book was returned

        self.stdout.write(f"  Created {len(returned_loans)} returned loans")

        total = len(active_loans) + len(overdue_loans) + len(returned_loans)
        self.stdout.write(f"  Total loans created: {total}")
