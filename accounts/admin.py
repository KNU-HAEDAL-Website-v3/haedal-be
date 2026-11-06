from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("동아리 정보", {"fields": ("is_approved", "max_loans")}),
    )
    list_display = ("username", "first_name", "is_approved", "max_loans", "is_staff")
    list_filter = ("is_approved",)
    list_editable = ("is_approved",)   # 목록에서 바로 승인 체크