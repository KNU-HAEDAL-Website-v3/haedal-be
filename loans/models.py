from django.conf import settings
from django.db import models
from books.models import BookCopy

class Loan(models.Model):
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="loans")
    copy = models.ForeignKey(BookCopy, on_delete=models.PROTECT, related_name="loans")
    loaned_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateField("반납 예정일")
    returned_at = models.DateTimeField("실제 반납일", null=True, blank=True)
    extension_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            # 한 실물에 '반납 전 대여 건'은 하나만 존재하도록 DB 수준에서 보장 (중복 대여 방지)
            models.UniqueConstraint(
                fields=["copy"],
                condition=models.Q(returned_at__isnull=True),
                name="unique_active_loan_per_copy",
            )
        ]

    def __str__(self):
        return f"{self.member} - {self.copy}"


class SystemPolicy(models.Model):
    """동아리 공통 대여 정책. pk=1 한 행만 사용한다."""

    max_rent_limit = models.PositiveIntegerField("1인당 최대 대여 개수", default=3)
    rent_period_days = models.PositiveIntegerField("기본 대여 기간(일)", default=7)
    max_extension_limit = models.PositiveIntegerField("최대 연장 가능 횟수", default=1)
    extension_days = models.PositiveIntegerField("1회 연장 시 추가 일수", default=7)

    class Meta:
        verbose_name = "시스템 정책"
        verbose_name_plural = "시스템 정책"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "시스템 정책"

    @classmethod
    def load(cls):
        policy, _created = cls.objects.get_or_create(pk=1)
        return policy


class Notification(models.Model):
    class Type(models.TextChoices):
        RENTAL = "RENTAL", "대여"
        RETURN = "RETURN", "반납"
        EXTENSION = "EXTENSION", "연장"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField("알림 유형", max_length=20, choices=Type.choices)
    message = models.CharField("알림 문구", max_length=500)
    is_read = models.BooleanField("읽음 여부", default=False)
    sent_at = models.DateTimeField("발송 일시", auto_now_add=True)

    def __str__(self):
        return f"{self.get_type_display()} - {self.user}"