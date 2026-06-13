from django.contrib import admin
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import path
from django.shortcuts import render
from django.contrib import messages
from django.utils.html import format_html
import json
import csv
from io import StringIO

from .models import (
    ChatMessage, KnowledgeBase,
    ChatbotResponseFlag, ChatbotResponseEdit,
    ChatbotKnowledgeModeration, ChatbotModerationAction,
    ChatbotQualityScore,
)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    """
    Admin interface for viewing and managing chat messages.
    """
    list_display = ('id', 'user', 'session_id_short', 'message_preview', 'response_preview', 'timestamp')
    list_filter = ('timestamp', 'user')
    search_fields = ('message', 'response', 'user__username', 'session_id')
    readonly_fields = ('timestamp', 'user', 'session_id', 'message', 'response')
    ordering = ('-timestamp',)
    date_hierarchy = 'timestamp'
    list_per_page = 50

    def session_id_short(self, obj):
        if obj.session_id:
            return obj.session_id[:8] + '...'
        return '-'
    session_id_short.short_description = 'Session ID'

    def message_preview(self, obj):
        return obj.message[:50] + '...' if len(obj.message) > 50 else obj.message
    message_preview.short_description = 'User Message'

    def response_preview(self, obj):
        return obj.response[:50] + '...' if len(obj.response) > 50 else obj.response
    response_preview.short_description = 'Bot Response'

    def has_add_permission(self, request):
        """Disable adding messages manually - they should come from the chatbot."""
        return False

    def has_change_permission(self, request, obj=None):
        """Disable editing messages - they are historical records."""
        return False

    actions = ['export_as_csv', 'export_as_json']

    @admin.action(description="Export selected messages as CSV")
    def export_as_csv(self, request, queryset):
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'User', 'Session ID', 'Message', 'Response', 'Timestamp'])

        for msg in queryset:
            writer.writerow([
                msg.id,
                msg.user.username if msg.user else 'anonymous',
                msg.session_id or '-',
                msg.message,
                msg.response,
                msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            ])

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="chat_messages.csv"'
        return response

    @admin.action(description="Export selected messages as JSON")
    def export_as_json(self, request, queryset):
        data = []
        for msg in queryset:
            data.append({
                'id': msg.id,
                'user': msg.user.username if msg.user else 'anonymous',
                'session_id': msg.session_id,
                'message': msg.message,
                'response': msg.response,
                'timestamp': msg.timestamp.isoformat()
            })

        response = HttpResponse(
            json.dumps(data, indent=2),
            content_type='application/json'
        )
        response['Content-Disposition'] = 'attachment; filename="chat_messages.json"'
        return response


@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(admin.ModelAdmin):
    """
    Admin interface for managing knowledge base entries.
    Includes import/export functionality and preview capabilities.
    """
    list_display = ('id', 'category', 'question_preview', 'answer_preview', 'keywords_preview', 'is_active', 'updated_at')
    list_filter = ('category', 'is_active', 'created_at', 'updated_at')
    search_fields = ('question', 'answer', 'keywords', 'category')
    list_editable = ('is_active',)
    ordering = ('-updated_at',)
    list_per_page = 25
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Question & Answer', {
            'fields': ('question', 'answer'),
            'description': 'Enter the question and its corresponding answer.'
        }),
        ('Classification', {
            'fields': ('category', 'keywords'),
            'description': 'Categorize the Q&A and add keywords for better matching.'
        }),
        ('Status', {
            'fields': ('is_active',),
            'description': 'Inactive entries will not be used by the chatbot.'
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    readonly_fields = ('created_at', 'updated_at')

    def question_preview(self, obj):
        return obj.question[:60] + '...' if len(obj.question) > 60 else obj.question
    question_preview.short_description = 'Question'

    def answer_preview(self, obj):
        return obj.answer[:60] + '...' if len(obj.answer) > 60 else obj.answer
    answer_preview.short_description = 'Answer'

    def keywords_preview(self, obj):
        keywords = obj.keywords.split(',')[:3]
        preview = ', '.join(k.strip() for k in keywords)
        if len(obj.keywords.split(',')) > 3:
            preview += '...'
        return preview
    keywords_preview.short_description = 'Keywords'

    actions = ['export_as_json', 'export_as_csv', 'activate_entries', 'deactivate_entries', 'reload_rag_engine']

    @admin.action(description="Export selected entries as JSON")
    def export_as_json(self, request, queryset):
        data = {
            'qa_pairs': []
        }
        for entry in queryset:
            data['qa_pairs'].append({
                'category': entry.category,
                'question': entry.question,
                'answer': entry.answer,
                'keywords': [k.strip() for k in entry.keywords.split(',') if k.strip()],
                'is_active': entry.is_active
            })

        response = HttpResponse(
            json.dumps(data, indent=2),
            content_type='application/json'
        )
        response['Content-Disposition'] = 'attachment; filename="knowledge_base_export.json"'
        return response

    @admin.action(description="Export selected entries as CSV")
    def export_as_csv(self, request, queryset):
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['Category', 'Question', 'Answer', 'Keywords', 'Is Active'])

        for entry in queryset:
            writer.writerow([
                entry.category,
                entry.question,
                entry.answer,
                entry.keywords,
                'Yes' if entry.is_active else 'No'
            ])

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="knowledge_base_export.csv"'
        return response

    @admin.action(description="Activate selected entries")
    def activate_entries(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} entries activated.", messages.SUCCESS)
        self._reload_engine(request)

    @admin.action(description="Deactivate selected entries")
    def deactivate_entries(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} entries deactivated.", messages.SUCCESS)
        self._reload_engine(request)

    @admin.action(description="Reload RAG Engine (apply changes)")
    def reload_rag_engine(self, request, queryset):
        self._reload_engine(request)

    def _reload_engine(self, request):
        """Reload the RAG engine to pick up new entries."""
        try:
            from .rag_engine import get_rag_engine
            engine = get_rag_engine()
            engine.reload_knowledge_base()
            self.message_user(
                request,
                "RAG engine reloaded successfully. New entries are now active.",
                messages.SUCCESS
            )
        except Exception as e:
            self.message_user(
                request,
                f"Failed to reload RAG engine: {str(e)}",
                messages.ERROR
            )

    def save_model(self, request, obj, form, change):
        """Auto-reload RAG engine when an entry is saved."""
        super().save_model(request, obj, form, change)
        self._reload_engine(request)

    def delete_model(self, request, obj):
        """Auto-reload RAG engine when an entry is deleted."""
        super().delete_model(request, obj)
        self._reload_engine(request)

    def delete_queryset(self, request, queryset):
        """Auto-reload RAG engine when entries are bulk deleted."""
        super().delete_queryset(request, queryset)
        self._reload_engine(request)

    change_list_template = 'admin/chatbot/knowledgebase/change_list.html'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('import/', self.admin_site.admin_view(self.import_view), name='chatbot_knowledgebase_import'),
        ]
        return custom_urls + urls

    def import_view(self, request):
        """Handle importing knowledge base entries from JSON or CSV."""
        if request.method == 'POST':
            file = request.FILES.get('import_file')
            if not file:
                messages.error(request, 'Please select a file to import.')
                return HttpResponseRedirect('../')

            try:
                content = file.read().decode('utf-8')
                file_name = file.name.lower()

                imported_count = 0

                if file_name.endswith('.json'):
                    data = json.loads(content)
                    qa_pairs = data.get('qa_pairs', data if isinstance(data, list) else [])

                    for qa in qa_pairs:
                        keywords = qa.get('keywords', [])
                        if isinstance(keywords, list):
                            keywords = ', '.join(keywords)

                        KnowledgeBase.objects.create(
                            question=qa.get('question', ''),
                            answer=qa.get('answer', ''),
                            category=qa.get('category', 'general'),
                            keywords=keywords,
                            is_active=qa.get('is_active', True)
                        )
                        imported_count += 1

                elif file_name.endswith('.csv'):
                    reader = csv.DictReader(StringIO(content))
                    for row in reader:
                        is_active = row.get('Is Active', 'Yes').lower() in ('yes', 'true', '1')
                        KnowledgeBase.objects.create(
                            question=row.get('Question', ''),
                            answer=row.get('Answer', ''),
                            category=row.get('Category', 'general'),
                            keywords=row.get('Keywords', ''),
                            is_active=is_active
                        )
                        imported_count += 1
                else:
                    messages.error(request, 'Unsupported file format. Please use JSON or CSV.')
                    return HttpResponseRedirect('../')

                # Reload RAG engine
                self._reload_engine(request)
                messages.success(request, f'Successfully imported {imported_count} entries.')

            except json.JSONDecodeError:
                messages.error(request, 'Invalid JSON file format.')
            except Exception as e:
                messages.error(request, f'Import failed: {str(e)}')

            return HttpResponseRedirect('../')

        # GET request - show import form
        context = {
            'title': 'Import Knowledge Base',
            'opts': self.model._meta,
        }
        return render(request, 'admin/chatbot/knowledgebase/import.html', context)


# =============================================================================
# MODERATION ADMIN REGISTRATIONS
# =============================================================================

@admin.register(ChatbotResponseFlag)
class ChatbotResponseFlagAdmin(admin.ModelAdmin):
    """Admin interface for managing chatbot response flags."""
    list_display = ('id_short', 'reason', 'severity', 'status', 'flagged_by', 'assigned_to', 'created_at')
    list_filter = ('status', 'severity', 'reason', 'created_at')
    search_fields = ('description', 'chat_message__message', 'chat_message__response')
    readonly_fields = ('id', 'created_at', 'updated_at', 'ip_address')
    ordering = ('-created_at',)
    list_per_page = 50

    def id_short(self, obj):
        return str(obj.id)[:8] + '...'
    id_short.short_description = 'ID'


@admin.register(ChatbotResponseEdit)
class ChatbotResponseEditAdmin(admin.ModelAdmin):
    """Admin interface for managing chatbot response edits."""
    list_display = ('id_short', 'edited_by', 'approval_status', 'edit_reason_preview', 'created_at')
    list_filter = ('approval_status', 'created_at')
    search_fields = ('edit_reason', 'original_response', 'edited_response')
    readonly_fields = ('id', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    list_per_page = 50

    def id_short(self, obj):
        return str(obj.id)[:8] + '...'
    id_short.short_description = 'ID'

    def edit_reason_preview(self, obj):
        return obj.edit_reason[:60] + '...' if len(obj.edit_reason) > 60 else obj.edit_reason
    edit_reason_preview.short_description = 'Reason'


@admin.register(ChatbotKnowledgeModeration)
class ChatbotKnowledgeModerationAdmin(admin.ModelAdmin):
    """Admin interface for knowledge base moderation history."""
    list_display = ('id_short', 'action', 'moderator', 'knowledge_entry', 'created_at')
    list_filter = ('action', 'created_at')
    search_fields = ('reason', 'new_question', 'new_answer')
    readonly_fields = ('id', 'created_at')
    ordering = ('-created_at',)
    list_per_page = 50

    def id_short(self, obj):
        return str(obj.id)[:8] + '...'
    id_short.short_description = 'ID'


@admin.register(ChatbotModerationAction)
class ChatbotModerationActionAdmin(admin.ModelAdmin):
    """Admin interface for moderation action log."""
    list_display = ('id_short', 'action_type', 'actor_username', 'description_preview', 'created_at')
    list_filter = ('action_type', 'created_at')
    search_fields = ('description', 'actor_username')
    readonly_fields = ('id', 'created_at', 'ip_address', 'metadata')
    ordering = ('-created_at',)
    list_per_page = 50

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def id_short(self, obj):
        return str(obj.id)[:8] + '...'
    id_short.short_description = 'ID'

    def description_preview(self, obj):
        return obj.description[:80] + '...' if len(obj.description) > 80 else obj.description
    description_preview.short_description = 'Description'


@admin.register(ChatbotQualityScore)
class ChatbotQualityScoreAdmin(admin.ModelAdmin):
    """Admin interface for chatbot quality scores."""
    list_display = ('id_short', 'chat_message', 'scored_by', 'overall_score', 'accuracy_score', 'helpfulness_score', 'tone_score', 'created_at')
    list_filter = ('overall_score', 'created_at')
    search_fields = ('notes', 'scored_by__username')
    readonly_fields = ('id', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    list_per_page = 50

    def id_short(self, obj):
        return str(obj.id)[:8] + '...'
    id_short.short_description = 'ID'
