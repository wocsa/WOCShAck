"""
Forum module URL configuration.
All URLs follow Django best practices with proper naming and patterns.
Includes comprehensive moderation endpoints for staff.
"""
from django.urls import path
from . import views
from . import views_extensions as views_ext

urlpatterns = [
    # Forum index
    path('', views.forum_index, name='forum_index'),

    # Category views
    path('category/<slug:slug>/', views.category_view, name='forum_category'),

    # Topic views
    path('topic/<uuid:topic_id>/', views.topic_view, name='forum_topic'),
    path('new-topic/', views.create_topic_general, name='forum_create_topic_general'),
    path('category/<slug:category_slug>/new/', views.create_topic, name='forum_create_topic'),
    path('topic/<uuid:topic_id>/reply/', views.create_reply, name='forum_create_reply'),

    # Post views
    path('post/<uuid:post_id>/edit/', views.edit_post, name='forum_edit_post'),
    path('post/<uuid:post_id>/delete/', views.delete_post, name='forum_delete_post'),
    path('post/<uuid:post_id>/like/', views.toggle_like, name='forum_toggle_like'),

    # Search
    path('search/', views.search, name='forum_search'),

    # User profile (forum-specific)
    path('user/<str:username>/', views.user_forum_profile, name='forum_user_profile'),

    # ==========================================================================
    # BOOKMARK URLs (Authenticated Users)
    # ==========================================================================
    path('post/<uuid:post_id>/bookmark/', views_ext.toggle_bookmark, name='forum_toggle_bookmark'),
    path('bookmarks/', views_ext.bookmark_list, name='forum_bookmarks'),

    # ==========================================================================
    # TAG SYSTEM URLs (Public + Authenticated)
    # ==========================================================================
    path('tag/<slug:tag_slug>/', views_ext.topics_by_tag, name='forum_topics_by_tag'),
    path('topic/<uuid:topic_id>/tag/add/', views_ext.add_tag_to_topic, name='forum_add_tag'),
    path('topic/<uuid:topic_id>/tag/<uuid:tag_id>/remove/', views_ext.remove_tag_from_topic, name='forum_remove_tag'),
    path('api/tags/autocomplete/', views_ext.tag_autocomplete, name='forum_tag_autocomplete'),

    # ==========================================================================
    # MENTION URLs (Public API)
    # ==========================================================================
    path('api/mentions/autocomplete/', views_ext.mention_autocomplete, name='forum_mention_autocomplete'),

    # ==========================================================================
    # QUOTE URL (Authenticated Users)
    # ==========================================================================
    path('post/<uuid:post_id>/quote/', views_ext.quote_post, name='forum_quote_post'),

    # ==========================================================================
    # USER BLOCKING URLs (Authenticated Users)
    # ==========================================================================
    path('user/<str:username>/block/', views_ext.toggle_block_user, name='forum_toggle_block'),
    path('blocked-users/', views_ext.blocked_users_list, name='forum_blocked_users'),

    # ==========================================================================
    # STICKY POST URL (Staff Only)
    # ==========================================================================
    path('post/<uuid:post_id>/sticky/', views_ext.toggle_sticky_post, name='forum_toggle_sticky'),

    # ==========================================================================
    # IMAGE UPLOAD URL (Authenticated Users)
    # ==========================================================================
    path('api/upload-image/', views_ext.upload_image, name='forum_upload_image'),

    # ==========================================================================
    # ADVANCED SEARCH URL (Public)
    # ==========================================================================
    path('search/advanced/', views_ext.advanced_search, name='forum_advanced_search'),

    # ==========================================================================
    # STATISTICS URL (Authenticated Users)
    # ==========================================================================
    path('statistics/', views_ext.forum_statistics, name='forum_statistics'),

    # ==========================================================================
    # RSS FEED URLs (Public)
    # ==========================================================================
    path('rss/', views_ext.rss_feed_latest, name='forum_rss_latest'),
    path('rss/category/<slug:slug>/', views_ext.rss_feed_category, name='forum_rss_category'),

    # ==========================================================================
    # SOCIAL SHARING URL (Public API)
    # ==========================================================================
    path('topic/<uuid:topic_id>/share/', views_ext.social_share, name='forum_social_share'),

    # ==========================================================================
    # NOTIFICATION URLs (Authenticated Users)
    # ==========================================================================
    path('notifications/', views_ext.notification_list, name='forum_notifications'),
    path('notifications/<uuid:notification_id>/read/', views_ext.mark_notification_read, name='forum_mark_notification_read'),
    path('notifications/mark-all-read/', views_ext.mark_all_notifications_read, name='forum_mark_all_notifications_read'),
    path('api/notifications/count/', views_ext.notification_count_api, name='forum_notification_count'),

    # ==========================================================================
    # MODERATION URLs (Staff Only)
    # ==========================================================================

    # Admin dashboard
    path('admin/', views.moderation_dashboard, name='forum_admin_dashboard'),
    path('admin/post/<uuid:post_id>/', views.moderate_post, name='forum_admin_post'),

    # User admin
    path('admin/user/<str:username>/', views.user_moderation, name='forum_user_admin'),

    # Warnings
    path('admin/user/<str:username>/warn/', views.issue_warning, name='forum_issue_warning'),
    path('admin/user/<str:username>/warnings/', views.view_warnings, name='forum_view_warnings'),

    # Muting
    path('admin/user/<str:username>/mute/', views.mute_user, name='forum_mute_user'),
    path('admin/user/<str:username>/unmute/', views.unmute_user, name='forum_unmute_user'),

    # Staff notes
    path('admin/user/<str:username>/notes/add/', views.add_staff_note, name='forum_add_staff_note'),

    # Reports
    path('admin/report/', views.report_content, name='forum_report_content'),
    path('admin/reports/', views.report_queue, name='forum_report_queue'),
    path('admin/reports/<uuid:report_id>/', views.report_detail, name='forum_report_detail'),
    path('admin/reports/analytics/', views.report_analytics, name='forum_report_analytics'),

    # Deleted content
    path('admin/deleted/', views.deleted_content_list, name='forum_deleted_content'),
    path('admin/deleted/<uuid:content_id>/', views.deleted_content_detail, name='forum_deleted_content_detail'),

    # Admin log
    path('admin/log/', views.moderation_log, name='forum_admin_log'),

    # ==========================================================================
    # BULK ADMIN URLs (Staff Only)
    # ==========================================================================
    path('admin/bulk/', views_ext.bulk_moderation, name='forum_bulk_admin'),
    path('admin/bulk/action/', views_ext.bulk_action, name='forum_bulk_action'),
]
