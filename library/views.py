from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import Author, Book, Member, Loan
from .serializers import AuthorSerializer, BookSerializer, MemberSerializer, LoanSerializer
from rest_framework.decorators import action

from datetime import date, timedelta
from django.db.models import Count, Q

from django.utils import timezone
from .tasks import send_loan_notification

class AuthorViewSet(viewsets.ModelViewSet):
    queryset = Author.objects.all()
    serializer_class = AuthorSerializer

class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.select_related('author').all()
    serializer_class = BookSerializer

    @action(detail=True, methods=['post'])
    def loan(self, request, pk=None):
        book = self.get_object()
        if book.available_copies < 1:
            return Response({'error': 'No available copies.'}, status=status.HTTP_400_BAD_REQUEST)
        member_id = request.data.get('member_id')
        try:
            member = Member.objects.get(id=member_id)
        except Member.DoesNotExist:
            return Response({'error': 'Member does not exist.'}, status=status.HTTP_400_BAD_REQUEST)
        loan = Loan.objects.create(book=book, member=member)
        book.available_copies -= 1
        book.save()
        send_loan_notification.delay(loan.id)
        return Response({'status': 'Book loaned successfully.'}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def return_book(self, request, pk=None):
        book = self.get_object()
        member_id = request.data.get('member_id')
        try:
            loan = Loan.objects.get(book=book, member__id=member_id, is_returned=False)
        except Loan.DoesNotExist:
            return Response({'error': 'Active loan does not exist.'}, status=status.HTTP_400_BAD_REQUEST)
        loan.is_returned = True
        loan.return_date = timezone.now().date()
        loan.save()
        book.available_copies += 1
        book.save()
        return Response({'status': 'Book returned successfully.'}, status=status.HTTP_200_OK)

class MemberViewSet(viewsets.ModelViewSet):
    queryset = Member.objects.all()
    serializer_class = MemberSerializer

    @action(detail=True, methods=['get'])
    def top_active(self, request):
        """
        Retrieve the top 5 members who currently have the most active loans active 
        """

        top_members = (
            Member.objects
            .annotate(active_loans=Count('loans', Q(loans__is_returned=False)))
            .filter(active_loans__gt=0)
            .select_related('user')[:5]
        )

        results = []

        for member in top_members:
             data = {
                "id": member.id,
                "username": member.user.username,
                "email": member.user.email,
                "active_loans": member.active_loans
             }


        return Response({'data': results}, status=status.HTTP_200_OK)


class LoanViewSet(viewsets.ModelViewSet):
    queryset = Loan.objects.all()
    serializer_class = LoanSerializer


    @action(detail=True, methods=['post'], url_path="extend_due_date")
    def extend_due_date(self, request, pk=None):
        """
        Endpoint to extend loan due date

        POST /api/loans/{loan_id}/extend_due_date/
        Payload: {"additional_days": 7}

        """

        # Get the loan or 404
        loan = self.get_object()

        # Get todays date
        today = date.today()

        # validate the loan has not been returned
        if loan.is_returned:
            return Response(
                {'error': 'The loan has been returned'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate that the loan is not already overdue.
        if loan.due_date < today:
            return Response(
                {'error': 'The due date of the loan has passed.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        

        try:
            additional_days = int(request.data.get('additional_days'))
        except (ValueError, TypeError):

            return Response(
                {'error': 'additional_days must be a positive integer'},
                status=status.HTTP_400_BAD_REQUEST
            )

        loan.due_date += timedelta(days=additional_days)
        loan.save()

        results = self.get_serializer(loan)

        return Response(data=results.data, status=status.HTTP_200_OK)