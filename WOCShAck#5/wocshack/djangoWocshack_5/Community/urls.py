from django.urls import path
from .views import (
    community_engagement_views,
    social_views,
    messaging_views,
    notification_views,
    follow_views,
    feed_views,
    blog_views,
    tutorial_views,
    showcase_views,
    event_views,
    reaction_views,
    moderation_views,
)


app_name = 'community'

urlpatterns = [
    # ── Index ────────────────────────────────────────────────────
    path('', community_engagement_views.index, name='index'),

    # ── Social — Friends ─────────────────────────────────────────
    path("friends/", social_views.friends_list, name="friends_list"),
    path("friends/requests/", social_views.friend_requests, name="friend_requests"),
    path("friends/send/", social_views.send_friend_request, name="send_friend_request"),
    path("friends/suppress_friend_request/", social_views.suppress_friend_request, name="suppress_friend_request"),
    path("friends/handle_request/<uuid:request_id>/", social_views.handle_friend_request, name="handle_friend_request"),
    path("friends/handle/<int:friend_id>/", social_views.handle_friend, name="handle_friend"),
    path("friends/suppr_friend/", social_views.suppr_friend, name="suppr_friend"),
    path("friends/block/", social_views.block_friend, name="block_friend"),
    path("friends/unblock/", social_views.unblock_friend, name="unblock_friend"),
    path("friends/add/", social_views.add_friends, name="add_friends"),

    # ── Social — Follow ──────────────────────────────────────────
    path("follow/<int:user_id>/", follow_views.follow_user, name="follow_user"),
    path("unfollow/<int:user_id>/", follow_views.unfollow_user, name="unfollow_user"),
    path("profile/<int:user_id>/followers/", follow_views.followers_list, name="followers_list"),
    path("profile/<int:user_id>/following/", follow_views.following_list, name="following_list"),

    # ── Messaging ────────────────────────────────────────────────
    path("messages/", messaging_views.inbox, name="inbox"),
    path("messages/start/<int:user_id>/", messaging_views.start_conversation, name="start_conversation"),
    path("messages/<uuid:conversation_id>/", messaging_views.conversation_detail, name="conversation_detail"),
    path("messages/report/<uuid:message_id>/", messaging_views.report_message, name="report_message"),
    path("messages/<uuid:conversation_id>/send/", messaging_views.send_message, name="send_message"),
    path("messages/edit/<uuid:message_id>/", messaging_views.edit_message, name="edit_message"),
    path("messages/delete/<uuid:message_id>/", messaging_views.delete_message, name="delete_message"),
    path("messages/transfer/<uuid:message_id>/", messaging_views.transfer_message, name="transfer_message"),
    path("messages/answer/<uuid:message_id>/", messaging_views.answer_message, name="answer_message"),

    # ── Notifications ────────────────────────────────────────────
    path("notifications/", notification_views.notifications_list, name="notifications_list"),
    path("notifications/read/<uuid:notif_id>/", notification_views.mark_notification_read, name="mark_notification_read"),
    path("notifications/read-all/", notification_views.mark_all_notifications_read, name="mark_all_read"),
    path("notifications/count/", notification_views.notifications_unread_count, name="notifications_count"),
    path("notifications/recent/", notification_views.notifications_recent, name="notifications_recent"),
    path("notifications/preferences/", notification_views.notification_preferences, name="notification_preferences"),

    # ── Activity Feed ────────────────────────────────────────────
    path("feed/", feed_views.activity_feed, name="activity_feed"),
    path("feed/settings/", feed_views.feed_preferences, name="feed_preferences"),

    # ── Profile (kept for compatibility) ─────────────────────────
    path("profile/<int:user_id>/", community_engagement_views.profile, name="user_profile"),

    # ── Blog & News ──────────────────────────────────────────────
    path("blog/", blog_views.blog_list, name="blog_list"),
    path("blog/create/", blog_views.blog_create, name="blog_create"),
    path("blog/<slug:slug>/", blog_views.blog_detail, name="blog_detail"),
    path("blog/<slug:slug>/edit/", blog_views.blog_edit, name="blog_edit"),
    path("blog/<slug:slug>/delete/", blog_views.blog_delete, name="blog_delete"),
    path("blog/<slug:slug>/comment/", blog_views.blog_comment_add, name="blog_comment_add"),

    # ── Tutorials ────────────────────────────────────────────────
    path("tutorials/", tutorial_views.tutorial_list, name="tutorial_list"),
    path("tutorials/create/", tutorial_views.tutorial_create, name="tutorial_create"),
    path("tutorials/<slug:slug>/", tutorial_views.tutorial_detail, name="tutorial_detail"),
    path("tutorials/<slug:slug>/edit/", tutorial_views.tutorial_edit, name="tutorial_edit"),
    path("tutorials/<slug:slug>/delete/", tutorial_views.tutorial_delete, name="tutorial_delete"),
    path("tutorials/<slug:slug>/step/<int:step_order>/", tutorial_views.tutorial_step, name="tutorial_step"),
    path("tutorials/<slug:slug>/step/<int:step_order>/quiz/", tutorial_views.tutorial_quiz_submit, name="tutorial_quiz"),
    path("tutorials/<slug:slug>/complete/", tutorial_views.tutorial_complete, name="tutorial_complete"),

    # ── Showcase Gallery ─────────────────────────────────────────
    path("showcase/", showcase_views.showcase_list, name="showcase_list"),
    path("showcase/submit/", showcase_views.showcase_submit, name="showcase_submit"),
    path("showcase/<uuid:item_id>/", showcase_views.showcase_detail, name="showcase_detail"),
    path("showcase/<uuid:item_id>/vote/", showcase_views.showcase_vote, name="showcase_vote"),

    # ── Events & Workshops ───────────────────────────────────────
    path("events/create/", event_views.event_create, name="event_create"),
    path("events/<uuid:event_id>/edit/", event_views.event_edit, name="event_edit"),
    path("events/<uuid:event_id>/delete/", event_views.event_delete, name="event_delete"),
    path("events/", event_views.event_list, name="event_list"),
    path("events/<uuid:event_id>/", event_views.event_detail, name="event_detail"),
    path("events/<uuid:event_id>/register/", event_views.event_register, name="event_register"),
    path("events/<uuid:event_id>/cancel/", event_views.event_cancel_registration, name="event_cancel"),

    # ── Reactions ────────────────────────────────────────────────
    path("react/", reaction_views.react, name="react"),
    path("reactions/", reaction_views.get_reactions, name="get_reactions"),

    # ── Moderation (Staff Only) ───────────────────────────────────────────────
    path("admin/", moderation_views.moderation_dashboard, name="admin_dashboard"),
    path("admin/blogs/", moderation_views.blog_list, name="admin_blog_list"),
    path("admin/blogs/<slug:slug>/delete/", moderation_views.blog_delete, name="admin_blog_delete"),
    path("admin/blog/categories/", blog_views.category_list, name="category_list"),
    path("admin/blog/categories/create/", blog_views.category_create, name="category_create"),
    path("admin/blog/categories/<slug:slug>/edit/", blog_views.category_edit, name="category_edit"),
    path("admin/blog/categories/<slug:slug>/delete/", blog_views.category_delete, name="category_delete"),
    path("admin/tutorials/", moderation_views.tutorial_list, name="admin_tutorial_list"),
    path("admin/tutorials/<slug:slug>/delete/", moderation_views.tutorial_delete, name="admin_tutorial_delete"),
    path("admin/showcase/", moderation_views.showcase_list, name="admin_showcase_list"),
    path("admin/showcase/action/", moderation_views.showcase_action, name="admin_showcase_action"),
    path("admin/messages/reports/", moderation_views.message_reports, name="admin_message_reports"),
    path("admin/messages/reports/<uuid:report_id>/resolve/", moderation_views.message_report_resolve, name="admin_message_report_resolve"),
    path("admin/events/", moderation_views.event_list, name="admin_event_list"),
    path("admin/events/<uuid:event_id>/cancel/", moderation_views.event_cancel, name="admin_event_cancel"),
]
