from django.contrib import admin
from .models import Loan

@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ("member", "copy", "loaned_at", "due_date", "returned_at", "extension_count")
    list_filter = ("due_date", "returned_at")
    search_fields = ("member__username", "copy__label_code")