"""
Chatbot module URL configuration.
All URLs follow Django best practices with proper naming and patterns.
Includes comprehensive moderation endpoints for staff.
"""
from django.urls import path
from . import views
from . import views_moderation as views_mod

app_name = 'chatbot'

urlpatterns = [
    # Main chatbot page
    path('', views.chatbot_index, name='index'),

    # API endpoints
    path('api/chat/', views.chat_api, name='chat_api'),
    path('api/history/', views.chat_history, name='history'),
    path('api/clear/', views.clear_history, name='clear_history'),
    path('api/categories/', views.get_categories, name='categories'),
    path('api/suggestions/', views.get_suggestions, name='suggestions'),
    path('api/export/', views.export_chat_history, name='export'),

    # User-facing flag endpoint (accessible to all users)
    path('api/flag/', views_mod.flag_response, name='flag_response'),

    # Embeddable widget
    path('widget/', views.chatbot_widget, name='widget'),

    # ==========================================================================
    # MODERATION URLs (Staff Only)
    # ==========================================================================

    # Moderation dashboard
    path('admin/', views_mod.moderation_dashboard, name='admin_dashboard'),

    # Flag management
    path('admin/flags/', views_mod.flag_queue, name='flag_queue'),
    path('admin/flags/<uuid:flag_id>/', views_mod.flag_detail, name='flag_detail'),
    path('admin/flags/<uuid:flag_id>/assign/', views_mod.flag_assign, name='flag_assign'),
    path('admin/flags/<uuid:flag_id>/resolve/', views_mod.flag_resolve, name='flag_resolve'),

    # Response editing
    path('admin/edit/<int:message_id>/', views_mod.edit_response, name='edit_response'),
    path('admin/edits/', views_mod.edit_queue, name='edit_queue'),
    path('admin/edits/<uuid:edit_id>/approve/', views_mod.approve_edit, name='approve_edit'),
    path('admin/edits/<uuid:edit_id>/reject/', views_mod.reject_edit, name='reject_edit'),

    # Knowledge base moderation
    path('admin/knowledge/', views_mod.knowledge_base_moderation, name='knowledge_base_admin'),
    path('admin/knowledge/create/', views_mod.create_kb_entry, name='create_kb_entry'),
    path('admin/knowledge/<int:entry_id>/toggle/', views_mod.toggle_kb_entry, name='toggle_kb_entry'),

    # Quality scoring
    path('admin/score/<int:message_id>/', views_mod.score_response, name='score_response'),

    # Statistics and analytics
    path('admin/statistics/', views_mod.moderation_statistics, name='admin_statistics'),

    # Action log
    path('admin/log/', views_mod.action_log, name='action_log'),

    # Browse messages
    path('admin/messages/', views_mod.browse_messages, name='browse_messages'),
]
