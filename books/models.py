from django.db import models

class Book(models.Model):
    title = models.CharField("도서명", max_length=200)
    author = models.CharField("저자", max_length=100, blank=True)

    def __str__(self):
        return self.title

class BookCopy(models.Model):
    """실물 한 권 = 라벨 하나. 시나리오의 '라벨'은 이 모델에 해당."""
    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "대여 가능"
        LOANED = "LOANED", "대여 중"
        LOST = "LOST", "분실"
        DAMAGED = "DAMAGED", "파손"

    book = models.ForeignKey(Book, on_delete=models.PROTECT, related_name="copies")
    label_code = models.CharField("라벨 코드", max_length=50, unique=True)  # 미등록 도서 판단 기준
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.AVAILABLE)
    location = models.CharField("보관 위치", max_length=100, blank=True)

    def __str__(self):
        return f"{self.book.title} [{self.label_code}]"