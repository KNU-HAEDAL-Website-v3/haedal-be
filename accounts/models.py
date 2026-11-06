from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    is_approved = models.BooleanField("운영진 승인 여부", default=False)  # 미승인 회원 처리
    max_loans = models.PositiveIntegerField("동시 대여 허용 권수", default=3)