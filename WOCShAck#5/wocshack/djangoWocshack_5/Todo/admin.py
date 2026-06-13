from django.contrib import admin
from .models import Mission


@admin.register(Mission)
class MissionAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'status', 'priority', 'category', 'due_date', 'is_staff_shared', 'created_at')
    list_filter = ('status', 'priority', 'is_staff_shared', 'category')
    search_fields = ('title', 'description', 'user__username')
    list_editable = ('status', 'priority')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
