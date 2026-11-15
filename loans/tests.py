from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from books.models import Book, BookCopy
from loans.models import Loan, Notification
from loans.services import RENT_PERIOD_DAYS, checkout, extend_loan, return_book


class LoanServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="member", password="pass")
        self.book = Book.objects.create(title="클린 코드", author="로버트 마틴")
        self.copy = BookCopy.objects.create(
            book=self.book,
            label_code="A-001",
            location="서가 1",
        )
        self.other_copy = BookCopy.objects.create(
            book=self.book,
            label_code="A-002",
            location="서가 1",
        )

    def test_checkout_creates_loan_and_notification(self):
        result = checkout(self.user.id, self.copy.id)

        self.copy.refresh_from_db()
        loan = Loan.objects.get(pk=result["data"]["rental_id"])
        today = timezone.localdate()

        self.assertTrue(result["success"])
        self.assertEqual(result["message"], "물품 대여가 완료되었습니다.")
        self.assertEqual(result["data"]["item_id"], self.copy.id)
        self.assertEqual(result["data"]["item_name"], "클린 코드")
        self.assertEqual(result["data"]["rental_date"], today.isoformat())
        self.assertEqual(result["data"]["return_date"], (today + timedelta(days=RENT_PERIOD_DAYS)).isoformat())
        self.assertEqual(self.copy.status, BookCopy.Status.LOANED)
        self.assertEqual(loan.due_date, today + timedelta(days=RENT_PERIOD_DAYS))
        self.assertIsNone(loan.returned_at)
        notice = Notification.objects.get(loan=loan)
        self.assertEqual(notice.type, Notification.Type.RENTAL)
        self.assertEqual(notice.user, self.user)
        self.assertFalse(notice.is_read)

    def test_checkout_rejects_when_rent_limit_is_reached(self):
        checkout(self.user.id, self.copy.id)
        checkout(self.user.id, self.other_copy.id)
        third = BookCopy.objects.create(book=self.book, label_code="A-003")
        checkout(self.user.id, third.id)
        extra = BookCopy.objects.create(book=self.book, label_code="A-004")

        with self.assertRaises(ValidationError) as caught:
            checkout(self.user.id, extra.id)

        extra.refresh_from_db()
        self.assertIn("최대 대여 개수", caught.exception.messages[0])
        self.assertEqual(extra.status, BookCopy.Status.AVAILABLE)
        self.assertEqual(Loan.objects.filter(returned_at__isnull=True).count(), 3)

    def test_checkout_rejects_unavailable_copy(self):
        self.copy.status = BookCopy.Status.LOST
        self.copy.save(update_fields=["status"])

        with self.assertRaises(ValidationError) as caught:
            checkout(self.user.id, self.copy.id)

        self.assertIn("분실", caught.exception.messages[0])
        self.assertFalse(Loan.objects.exists())

    def test_checkout_rejects_unknown_user_and_book(self):
        with self.assertRaises(ValidationError):
            checkout(9999, self.copy.id)
        with self.assertRaises(ValidationError):
            checkout(self.user.id, 9999)
        self.copy.refresh_from_db()
        self.assertEqual(self.copy.status, BookCopy.Status.AVAILABLE)

    def test_checkout_rolls_back_when_notification_fails(self):
        with patch("loans.services.Notification.objects.create", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                checkout(self.user.id, self.copy.id)

        self.copy.refresh_from_db()
        self.assertEqual(self.copy.status, BookCopy.Status.AVAILABLE)
        self.assertFalse(Loan.objects.exists())
        self.assertFalse(Notification.objects.exists())

    def test_return_book_restores_copy_and_records_notification(self):
        rental_id = checkout(self.user.id, self.copy.id)["data"]["rental_id"]

        result = return_book(rental_id)

        self.copy.refresh_from_db()
        loan = Loan.objects.get(pk=rental_id)
        self.assertTrue(result["success"])
        self.assertEqual(result["message"], "물품 반납이 완료되었습니다.")
        self.assertEqual(result["data"]["return_date"], timezone.localdate().isoformat())
        self.assertEqual(self.copy.status, BookCopy.Status.AVAILABLE)
        self.assertEqual(timezone.localtime(loan.returned_at).date(), timezone.localdate())
        self.assertTrue(
            Notification.objects.filter(loan=loan, type=Notification.Type.RETURN).exists()
        )

    def test_return_book_rejects_duplicate_return(self):
        rental_id = checkout(self.user.id, self.copy.id)["data"]["rental_id"]
        return_book(rental_id)

        with self.assertRaises(ValidationError) as caught:
            return_book(rental_id)

        self.assertIn("이미 반납된 물품", caught.exception.messages[0])

    def test_return_book_rejects_unknown_rental(self):
        with self.assertRaises(ValidationError) as caught:
            return_book(9999)
        self.assertIn("유효하지 않은 대여", caught.exception.messages[0])

    def test_extend_loan_pushes_due_date(self):
        rental_id = checkout(self.user.id, self.copy.id)["data"]["rental_id"]
        original_due = Loan.objects.get(pk=rental_id).due_date

        result = extend_loan(rental_id)

        loan = Loan.objects.get(pk=rental_id)
        self.copy.refresh_from_db()
        self.assertTrue(result["success"])
        self.assertEqual(result["message"], "대여 기한이 연장되었습니다.")
        self.assertEqual(loan.due_date, original_due + timedelta(days=7))
        self.assertEqual(result["data"]["return_date"], loan.due_date.isoformat())
        self.assertEqual(loan.extension_count, 1)
        self.assertEqual(self.copy.status, BookCopy.Status.LOANED)
        self.assertTrue(
            Notification.objects.filter(loan=loan, type=Notification.Type.EXTENSION).exists()
        )

    def test_extend_loan_rejects_when_period_is_exhausted(self):
        rental_id = checkout(self.user.id, self.copy.id)["data"]["rental_id"]
        extend_loan(rental_id)

        with self.assertRaises(ValidationError) as caught:
            extend_loan(rental_id)

        loan = Loan.objects.get(pk=rental_id)
        self.assertIn("최대 연장", caught.exception.messages[0])
        self.assertEqual(loan.extension_count, 1)

    def test_extend_loan_rejects_returned_book(self):
        rental_id = checkout(self.user.id, self.copy.id)["data"]["rental_id"]
        return_book(rental_id)

        with self.assertRaises(ValidationError) as caught:
            extend_loan(rental_id)

        self.assertIn("이미 반납된 물품", caught.exception.messages[0])

    def test_checkout_rejects_when_user_has_overdue_item(self):
        checkout(self.user.id, self.copy.id)
        loan = Loan.objects.get(copy=self.copy)
        loan.due_date = timezone.localdate() - timedelta(days=1)
        loan.save(update_fields=["due_date"])

        with self.assertRaises(ValidationError) as caught:
            checkout(self.user.id, self.other_copy.id)

        self.other_copy.refresh_from_db()
        self.assertIn("연체", caught.exception.messages[0])
        self.assertEqual(self.other_copy.status, BookCopy.Status.AVAILABLE)

    def test_extend_loan_rejects_when_overdue(self):
        rental_id = checkout(self.user.id, self.copy.id)["data"]["rental_id"]
        loan = Loan.objects.get(pk=rental_id)
        loan.due_date = timezone.localdate() - timedelta(days=1)
        loan.save(update_fields=["due_date"])

        with self.assertRaises(ValidationError) as caught:
            extend_loan(rental_id)

        loan.refresh_from_db()
        self.assertIn("연체", caught.exception.messages[0])
        self.assertEqual(loan.extension_count, 0)
