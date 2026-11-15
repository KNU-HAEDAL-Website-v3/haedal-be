"""물품 대여, 반납, 연장.

실물 물품 모델은 아직 BookCopy다. checkout의 item_id는 그 실물 id다.
도서와 장비를 같은 대여 흐름으로 다루기 위해 응답 필드는 item_id, item_name을 쓴다.
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import User
from books.models import BookCopy
from loans.models import Loan, Notification

MAX_RENT_LIMIT = 3
RENT_PERIOD_DAYS = 14
MAX_EXTENSION_LIMIT = 1
EXTENSION_DAYS = 7


def _get_user_for_update(user_id: int) -> User:
    try:
        return User.objects.select_for_update().get(pk=user_id)
    except User.DoesNotExist:
        raise ValidationError("존재하지 않는 회원입니다.") from None


def _get_copy_for_update(item_id: int) -> BookCopy:
    try:
        return BookCopy.objects.select_for_update().select_related("book").get(pk=item_id)
    except BookCopy.DoesNotExist:
        raise ValidationError("존재하지 않는 물품입니다.") from None


def _get_loan_for_update(rental_id: int) -> Loan:
    try:
        return (
            Loan.objects.select_for_update()
            .select_related("member", "copy", "copy__book")
            .get(pk=rental_id)
        )
    except Loan.DoesNotExist:
        raise ValidationError("유효하지 않은 대여 정보입니다.") from None


def _active_loans(user: User) -> list[Loan]:
    # count()는 집계 쿼리로 바뀌며 행 잠금이 빠질 수 있어, 대여 행을 잠근 뒤 센다.
    return list(
        Loan.objects.select_for_update().filter(member=user, returned_at__isnull=True)
    )


def _item_name(copy: BookCopy) -> str:
    return copy.book.title


def _reject_if_overdue(loans: list[Loan], today, message: str) -> None:
    if any(loan.due_date < today for loan in loans):
        raise ValidationError(message)


def _notify(user, loan: Loan, notice_type: str, message: str) -> Notification:
    return Notification.objects.create(
        user=user,
        loan=loan,
        type=notice_type,
        message=message,
    )


def _reject_unavailable_copy(copy: BookCopy) -> None:
    messages = {
        BookCopy.Status.LOANED: "이미 대여 중인 물품입니다.",
        BookCopy.Status.LOST: "분실 처리된 물품은 대여할 수 없습니다.",
        BookCopy.Status.DAMAGED: "파손 처리된 물품은 대여할 수 없습니다.",
    }
    if copy.status != BookCopy.Status.AVAILABLE:
        raise ValidationError(messages.get(copy.status, "대여할 수 없는 물품입니다."))


@transaction.atomic
def checkout(user_id: int, item_id: int) -> dict:
    user = _get_user_for_update(user_id)
    today = timezone.localdate()
    active = _active_loans(user)
    _reject_if_overdue(active, today, "연체 중인 물품이 있어 대여할 수 없습니다.")
    if len(active) >= MAX_RENT_LIMIT:
        raise ValidationError(
            f"1인당 최대 대여 개수({MAX_RENT_LIMIT}개)를 초과하여 대여할 수 없습니다. "
            f"현재 대여 중인 물품은 {len(active)}개입니다."
        )

    copy = _get_copy_for_update(item_id)
    _reject_unavailable_copy(copy)

    due_date = today + timedelta(days=RENT_PERIOD_DAYS)
    copy.status = BookCopy.Status.LOANED
    copy.save(update_fields=["status"])

    try:
        with transaction.atomic():
            loan = Loan.objects.create(member=user, copy=copy, due_date=due_date)
    except IntegrityError:
        raise ValidationError("이미 대여 중인 물품입니다.") from None

    item_name = _item_name(copy)
    _notify(
        user,
        loan,
        Notification.Type.RENTAL,
        f"'{item_name}' 물품을 대여했습니다. 반납 예정일은 {due_date.isoformat()}입니다.",
    )

    return {
        "success": True,
        "message": "물품 대여가 완료되었습니다.",
        "data": {
            "rental_id": loan.pk,
            "user_id": user.pk,
            "item_id": copy.pk,
            "item_name": item_name,
            "rental_date": timezone.localtime(loan.loaned_at).date().isoformat(),
            "return_date": due_date.isoformat(),
        },
    }


@transaction.atomic
def return_book(rental_id: int) -> dict:
    loan = _get_loan_for_update(rental_id)
    copy = _get_copy_for_update(loan.copy_id)

    if loan.returned_at is not None or copy.status == BookCopy.Status.AVAILABLE:
        raise ValidationError("이미 반납된 물품입니다.")
    if copy.status != BookCopy.Status.LOANED:
        raise ValidationError("현재 대여 중인 물품만 반납할 수 있습니다.")

    today = timezone.localdate()
    copy.status = BookCopy.Status.AVAILABLE
    copy.save(update_fields=["status"])
    loan.returned_at = timezone.now()
    loan.save(update_fields=["returned_at"])

    item_name = _item_name(copy)
    _notify(
        loan.member,
        loan,
        Notification.Type.RETURN,
        f"'{item_name}' 물품이 반납되었습니다.",
    )

    return {
        "success": True,
        "message": "물품 반납이 완료되었습니다.",
        "data": {
            "rental_id": loan.pk,
            "user_id": loan.member_id,
            "item_id": copy.pk,
            "item_name": item_name,
            "return_date": today.isoformat(),
        },
    }


@transaction.atomic
def extend_loan(rental_id: int) -> dict:
    try:
        member_id = Loan.objects.values_list("member_id", flat=True).get(pk=rental_id)
    except Loan.DoesNotExist:
        raise ValidationError("유효하지 않은 대여 정보입니다.") from None

    # 대여 행보다 회원을 먼저 잠가야 checkout과 순서가 엇갈리지 않는다.
    user = _get_user_for_update(member_id)
    loan = _get_loan_for_update(rental_id)
    today = timezone.localdate()
    _reject_if_overdue(
        _active_loans(user),
        today,
        "연체 중인 물품이 있어 연장할 수 없습니다.",
    )
    copy = _get_copy_for_update(loan.copy_id)

    if loan.returned_at is not None or copy.status == BookCopy.Status.AVAILABLE:
        raise ValidationError("이미 반납된 물품은 연장할 수 없습니다.")
    if copy.status != BookCopy.Status.LOANED:
        raise ValidationError("현재 대여 중인 물품만 연장할 수 있습니다.")
    if loan.extension_count >= MAX_EXTENSION_LIMIT:
        raise ValidationError(
            f"최대 연장 가능 횟수({MAX_EXTENSION_LIMIT}회)를 초과하여 연장할 수 없습니다."
        )

    loan.due_date = loan.due_date + timedelta(days=EXTENSION_DAYS)
    loan.extension_count += 1
    loan.save(update_fields=["due_date", "extension_count"])

    item_name = _item_name(copy)
    _notify(
        loan.member,
        loan,
        Notification.Type.EXTENSION,
        f"'{item_name}' 물품의 반납 기한이 {loan.due_date.isoformat()}로 연장되었습니다.",
    )

    return {
        "success": True,
        "message": "대여 기한이 연장되었습니다.",
        "data": {
            "rental_id": loan.pk,
            "user_id": loan.member_id,
            "item_id": copy.pk,
            "item_name": item_name,
            "return_date": loan.due_date.isoformat(),
            "extension_count": loan.extension_count,
        },
    }
