from django.contrib import admin
from .models import Loan, Notification, SystemPolicy

@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ("member", "copy", "loaned_at", "due_date", "returned_at", "extension_count")
    list_filter = ("due_date", "returned_at")
    search_fields = ("member__username", "copy__label_code")


@admin.register(SystemPolicy)
class SystemPolicyAdmin(admin.ModelAdmin):
    list_display = ("max_rent_limit", "rent_period_days", "max_extension_limit", "extension_days")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "loan", "type", "is_read", "sent_at")
    list_filter = ("type", "is_read")
    search_fields = ("message", "user__username")