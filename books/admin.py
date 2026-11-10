from django.contrib import admin
from .models import Book, BookCopy

class BookCopyInline(admin.TabularInline):
    model = BookCopy
    extra = 1

@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("title", "author")
    search_fields = ("title", "author")
    inlines = [BookCopyInline]     # 도서 등록 화면에서 라벨도 함께 등록

@admin.register(BookCopy)
class BookCopyAdmin(admin.ModelAdmin):
    list_display = ("label_code", "book", "status", "location")
    list_filter = ("status",)
    search_fields = ("label_code", "book__title")