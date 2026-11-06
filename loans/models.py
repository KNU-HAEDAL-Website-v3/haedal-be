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