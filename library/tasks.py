from datetime import date

from celery import shared_task
from .models import Loan
from django.core.mail import send_mail
from django.conf import settings

@shared_task
def send_loan_notification(loan_id):
    try:
        loan = Loan.objects.get(id=loan_id)
        member_email = loan.member.user.email
        book_title = loan.book.title
        send_mail(
            subject='Book Loaned Successfully',
            message=f'Hello {loan.member.user.username},\n\nYou have successfully loaned "{book_title}".\nPlease return it by the due date.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[member_email],
            fail_silently=False,
        )
    except Loan.DoesNotExist:
        pass


@shared_task
def check_overdue_loans():
    """
    It checks over due loans then sends email to the user.

    Validations:
        1. Check if loan is not returned and due date has pased.
        2. Uses select_related to minimize N+1 queries when fetching user and book details
    """

    # Get todays date
    today = date.today()

    overdue_loans = Loan.objects.filter(
        is_returned=False,
        due_date__lt=today
        ).select_related('member__user', 'book')

    for loan in overdue_loans:
        book = loan.book
        user = loan.member.user

        send_mail(
            subject=f"Overdue Loan for {book.title}",
            message=(
                f'Hello {user.username},\n'
                f'You have an over loan of {book.title}. '
                f'It was due by {loan.due_date}.\n'
                f'Kindly return it as soon as possible.'
            ),
            recipient_list=[user.email],
            fail_silently=False,
        )
    
    # we can use this for logging
    return f"Processed {overdue_loans.count()} loan(s)"
    