"""
API URL configuration for CSS marketplace.
All endpoints follow RESTful conventions with proper HTTP method restrictions.
"""
from django.urls import path
from . import views
from . import views_account
from . import views_bank
from . import views_shopping
from . import views_forum
from . import views_chatbot
from . import views_advertisement
from . import views_community
from . import views_developer
from . import views_moderation


urlpatterns = [
    # ==========================================================================
    # API Root & Documentation
    # ==========================================================================
    path("", views.api, name="api"),
    path("docs/", views.api_docs_view, name="api_docs"),
    path("openapi.json", views.openapi_spec, name="openapi_spec"),
    path("health/", views.health_view, name="api_health"),

    # ==========================================================================
    # Account API Endpoints
    # ==========================================================================
    path("account/profile/", views_account.profile_view, name="api_account_profile"),
    path("account/profile/<str:username>/", views_account.public_profile_view, name="api_account_public_profile"),
    path("account/sessions/", views_account.sessions_view, name="api_account_sessions"),
    path("account/sessions/<int:session_id>/", views_account.revoke_session_view, name="api_account_revoke_session"),
    path("account/login-history/", views_account.login_history_view, name="api_account_login_history"),
    path("account/2fa/status/", views_account.two_factor_status_view, name="api_account_2fa_status"),
    path("account/backup-codes/", views_account.backup_codes_view, name="api_account_backup_codes"),
    path("account/store/", views_account.store_view, name="api_account_store"),
    path("account/users/search/", views_account.user_search_view, name="api_account_user_search"),
    path("account/password/change/", views_account.password_change_view, name="api_account_password_change"),

    # ==========================================================================
    # Bank API Endpoints
    # ==========================================================================
    path("bank/balance/", views_bank.balance_view, name="api_bank_balance"),
    path("bank/transactions/", views_bank.transactions_view, name="api_bank_transactions"),
    path("bank/transactions/<int:transaction_id>/", views_bank.transactions_view, name="api_bank_transactions_detail"),
    path("bank/cards/", views_bank.cards_view, name="api_bank_cards"),
    path("bank/transfer/", views_bank.transfer_view, name="api_bank_transfer"),
    path("bank/beneficiaries/", views_bank.beneficiaries_view, name="api_bank_beneficiaries"),
    path("bank/beneficiaries/<int:beneficiary_id>/", views_bank.beneficiary_delete_view, name="api_bank_beneficiaries_delete"),
    path("bank/export/", views_bank.export_view, name="api_bank_export"),
    path("bank/cards/generate/", views_bank.card_generate_view, name="api_bank_card_generate"),
    path("bank/cards/<int:card_id>/freeze/", views_bank.card_freeze_view, name="api_bank_card_freeze"),
    path("bank/cards/<int:card_id>/toggle-status/", views_bank.card_toggle_view, name="api_bank_card_toggle"),
    path("bank/statement/", views_bank.statement_view, name="api_bank_statement"),

    # ==========================================================================
    # Shopping API Endpoints
    # ==========================================================================
    path("shop/products/", views_shopping.products_view, name="api_shop_products"),
    path("shop/products/<uuid:css_id>/", views_shopping.products_view, name="api_shop_products_detail"),
    path("shop/cart/", views_shopping.cart_view, name="api_shop_cart"),
    path("shop/cart/add/", views_shopping.cart_add_view, name="api_shop_cart_add"),
    path("shop/cart/update/", views_shopping.cart_update_view, name="api_shop_cart_update"),
    path("shop/cart/remove/<uuid:css_id>/", views_shopping.cart_remove_view, name="api_shop_cart_remove"),
    path("shop/checkout/", views_shopping.checkout_view, name="api_shop_checkout"),
    path("shop/orders/", views_shopping.orders_view, name="api_shop_orders"),
    path("shop/orders/<uuid:order_id>/", views_shopping.orders_view, name="api_shop_orders_detail"),
    path("shop/coupon/apply/", views_shopping.coupon_apply_view, name="api_shop_coupon_apply"),
    path("shop/wishlist/", views_shopping.wishlist_view, name="api_shop_wishlist"),
    path("shop/wishlist/add/<uuid:css_id>/", views_shopping.wishlist_add_view, name="api_shop_wishlist_add"),
    path("shop/wishlist/remove/<uuid:css_id>/", views_shopping.wishlist_remove_view, name="api_shop_wishlist_remove"),
    path("shop/reviews/<uuid:css_id>/", views_shopping.reviews_view, name="api_shop_reviews"),

    # ==========================================================================
    # Forum API Endpoints
    # ==========================================================================
    path("forum/categories/", views_forum.categories_view, name="api_forum_categories"),
    path("forum/topics/", views_forum.topics_view, name="api_forum_topics"),
    path("forum/topics/<uuid:topic_id>/", views_forum.topic_detail_view, name="api_forum_topic_detail"),
    path("forum/topics/<uuid:topic_id>/reply/", views_forum.topic_reply_view, name="api_forum_topic_reply"),
    path("forum/posts/<uuid:post_id>/", views_forum.post_detail_view, name="api_forum_post_detail"),
    path("forum/posts/<uuid:post_id>/like/", views_forum.toggle_like_view, name="api_forum_post_like"),
    path("forum/search/", views_forum.forum_search_view, name="api_forum_search"),
    path("forum/tags/", views_forum.tags_view, name="api_forum_tags"),
    path("forum/tags/<slug:slug>/topics/", views_forum.tag_topics_view, name="api_forum_tag_topics"),
    path("forum/notifications/", views_forum.notifications_view, name="api_forum_notifications"),
    path("forum/notifications/read-all/", views_forum.notifications_read_all_view, name="api_forum_notifications_read_all"),
    path("forum/statistics/", views_forum.statistics_view, name="api_forum_statistics"),
    path("forum/reputation/<str:username>/", views_forum.reputation_view, name="api_forum_reputation"),
    path("forum/bookmarks/", views_forum.bookmarks_view, name="api_forum_bookmarks"),
    path("forum/posts/<uuid:post_id>/bookmark/", views_forum.toggle_bookmark_view, name="api_forum_post_bookmark"),

    # ==========================================================================
    # Chatbot API Endpoints
    # ==========================================================================
    path("chatbot/chat/", views_chatbot.chat_view, name="api_chatbot_chat"),
    path("chatbot/history/", views_chatbot.history_view, name="api_chatbot_history"),
    path("chatbot/history/clear/", views_chatbot.clear_history_view, name="api_chatbot_history_clear"),
    path("chatbot/categories/", views_chatbot.categories_view, name="api_chatbot_categories"),
    path("chatbot/suggestions/", views_chatbot.suggestions_view, name="api_chatbot_suggestions"),
    path("chatbot/export/", views_chatbot.export_view, name="api_chatbot_export"),
    path("chatbot/flag/", views_chatbot.flag_view, name="api_chatbot_flag"),

    # ==========================================================================
    # Advertisement API Endpoints
    # ==========================================================================
    path("ads/serve/", views_advertisement.serve_ad_view, name="api_ads_serve"),
    path("ads/impression/<uuid:ad_id>/", views_advertisement.impression_view, name="api_ads_impression"),
    path("ads/click/<uuid:ad_id>/", views_advertisement.click_view, name="api_ads_click"),
    path("ads/campaigns/", views_advertisement.campaigns_view, name="api_ads_campaigns"),
    path("ads/", views_advertisement.ads_list_view, name="api_ads_list"),
    path("ads/<uuid:ad_id>/", views_advertisement.ad_detail_view, name="api_ads_detail"),
    path("ads/<uuid:ad_id>/activate/", views_advertisement.activate_ad_view, name="api_ads_activate"),
    path("ads/dashboard/", views_advertisement.dashboard_view, name="api_ads_dashboard"),
    path("ads/<uuid:ad_id>/stats/", views_advertisement.ad_stats_view, name="api_ads_stats"),
    path("ads/admin/pending/", views_advertisement.admin_pending_view, name="api_ads_admin_pending"),
    path("ads/admin/approve/<uuid:ad_id>/", views_advertisement.admin_approve_view, name="api_ads_admin_approve"),
    path("ads/admin/reject/<uuid:ad_id>/", views_advertisement.admin_reject_view, name="api_ads_admin_reject"),

    # ==========================================================================
    # Community API Endpoints
    # ==========================================================================
    # Friends
    path("community/friends/", views_community.friends_view, name="api_community_friends"),
    path("community/friends/add/", views_community.friend_add_view, name="api_community_friends_add"),
    path("community/friends/requests/<int:request_id>/", views_community.friend_handle_view, name="api_community_friend_handle"),
    path("community/friends/remove/<int:friend_id>/", views_community.friend_remove_view, name="api_community_friend_remove"),
    path("community/friends/block/", views_community.friend_block_view, name="api_community_friend_block"),
    path("community/friends/unblock/", views_community.friend_unblock_view, name="api_community_friend_unblock"),
    # Follow
    path("community/follow/<int:user_id>/", views_community.follow_view, name="api_community_follow"),
    path("community/unfollow/<int:user_id>/", views_community.unfollow_view, name="api_community_unfollow"),
    # Messages
    path("community/messages/", views_community.messages_view, name="api_community_messages"),
    path("community/messages/send/", views_community.messages_send_view, name="api_community_messages_send"),
    path("community/messages/<uuid:conversation_id>/", views_community.conversation_detail_view, name="api_community_conversation_detail"),
    path("community/messages/start/<int:user_id>/", views_community.conversation_start_view, name="api_community_conversation_start"),
    # Notifications
    path("community/notifications/", views_community.notifications_view, name="api_community_notifications"),
    path("community/notifications/count/", views_community.notification_count_view, name="api_community_notification_count"),
    path("community/notifications/read-all/", views_community.notification_read_all_view, name="api_community_notification_read_all"),
    path("community/notifications/<uuid:notification_id>/read/", views_community.notification_read_view, name="api_community_notification_read"),
    # Feed
    path("community/feed/", views_community.feed_view, name="api_community_feed"),
    # Events
    path("community/events/", views_community.events_view, name="api_community_events"),
    path("community/events/<uuid:event_id>/", views_community.event_detail_view, name="api_community_event_detail"),
    path("community/events/<uuid:event_id>/register/", views_community.event_register_view, name="api_community_event_register"),
    path("community/events/<uuid:event_id>/cancel/", views_community.event_cancel_view, name="api_community_event_cancel"),
    # Blog
    path("community/blog/", views_community.blog_view, name="api_community_blog"),
    path("community/blog/<slug:slug>/", views_community.blog_detail_view, name="api_community_blog_detail"),
    path("community/blog/<slug:slug>/comments/", views_community.blog_comment_view, name="api_community_blog_comment"),
    # Tutorials
    path("community/tutorials/", views_community.tutorials_view, name="api_community_tutorials"),
    path("community/tutorials/<slug:slug>/", views_community.tutorial_detail_view, name="api_community_tutorial_detail"),
    # Showcase
    path("community/showcase/", views_community.showcase_view, name="api_community_showcase"),
    path("community/showcase/submit/", views_community.showcase_submit_view, name="api_community_showcase_submit"),
    path("community/showcase/<uuid:item_id>/", views_community.showcase_detail_view, name="api_community_showcase_detail"),
    path("community/showcase/<uuid:item_id>/vote/", views_community.showcase_vote_view, name="api_community_showcase_vote"),
    # Reactions
    path("community/reactions/", views_community.reactions_view, name="api_community_reactions"),
    # CSS Comments
    path("community/css-comments/<uuid:css_id>/", views_community.css_comments_view, name="api_community_css_comments"),

    # ==========================================================================
    # Developer API Endpoints
    # ==========================================================================
    # Profile
    path("developer/profile/", views_developer.profile_view, name="api_developer_profile"),
    path("developer/profile/<str:username>/", views_developer.public_profile_view, name="api_developer_public_profile"),
    # Plans & Subscription
    path("developer/plans/", views_developer.plans_view, name="api_developer_plans"),
    path("developer/subscription/", views_developer.subscription_view, name="api_developer_subscription"),
    path("developer/subscribe/<slug:slug>/", views_developer.subscribe_view, name="api_developer_subscribe"),
    path("developer/subscription/cancel/", views_developer.cancel_subscription_view, name="api_developer_subscription_cancel"),
    # Projects
    path("developer/projects/", views_developer.projects_view, name="api_developer_projects"),
    path("developer/projects/<uuid:project_id>/", views_developer.project_detail_view, name="api_developer_project_detail"),
    path("developer/projects/<uuid:project_id>/versions/", views_developer.project_versions_view, name="api_developer_project_versions"),
    # Listings
    path("developer/listings/", views_developer.listings_view, name="api_developer_listings"),
    path("developer/listings/<uuid:listing_id>/", views_developer.listing_detail_view, name="api_developer_listing_detail"),
    # Analytics
    path("developer/analytics/", views_developer.analytics_overview_view, name="api_developer_analytics"),
    path("developer/analytics/revenue/", views_developer.analytics_revenue_view, name="api_developer_analytics_revenue"),
    path("developer/analytics/products/", views_developer.analytics_products_view, name="api_developer_analytics_products"),
    path("developer/analytics/customers/", views_developer.analytics_customers_view, name="api_developer_analytics_customers"),
    path("developer/analytics/export/", views_developer.analytics_export_view, name="api_developer_analytics_export"),
    # Webhooks
    path("developer/webhooks/", views_developer.webhooks_view, name="api_developer_webhooks"),
    path("developer/webhooks/<uuid:webhook_id>/", views_developer.webhook_detail_view, name="api_developer_webhook_detail"),
    path("developer/webhooks/<uuid:webhook_id>/test/", views_developer.webhook_test_view, name="api_developer_webhook_test"),
    path("developer/webhooks/<uuid:webhook_id>/logs/", views_developer.webhook_logs_view, name="api_developer_webhook_logs"),
    # Balance & Payouts
    path("developer/balance/", views_developer.balance_view, name="api_developer_balance"),
    path("developer/payouts/", views_developer.payouts_view, name="api_developer_payouts"),
    path("developer/payouts/request/", views_developer.payouts_request_view, name="api_developer_payouts_request"),
    # Promotions
    path("developer/promotions/", views_developer.promotions_view, name="api_developer_promotions"),
    path("developer/promotions/<uuid:promo_id>/", views_developer.promotion_delete_view, name="api_developer_promotion_delete"),
    # CSS Tools
    path("developer/tools/minify/", views_developer.tools_minify_view, name="api_developer_tools_minify"),
    path("developer/tools/beautify/", views_developer.tools_beautify_view, name="api_developer_tools_beautify"),
    path("developer/tools/validate/", views_developer.tools_validate_view, name="api_developer_tools_validate"),
    path("developer/tools/prefix/", views_developer.tools_prefix_view, name="api_developer_tools_prefix"),

    # ==========================================================================
    # API Key Management
    # ==========================================================================
    path("keys/", views.api_keys_page, name="api_keys"),
    path("keys/create/", views.create_api_key, name="create_api_key"),
    path("keys/revoke/<uuid:key_id>/", views.revoke_api_key, name="revoke_api_key"),
    path("keys/<uuid:key_id>/", views.single_key_detail, name="api_key_detail"),
    path("keys/<uuid:key_id>/regenerate/", views.regenerate_api_key, name="regenerate_api_key"),
    path("keys/<uuid:key_id>/usage/", views.api_key_usage, name="api_key_usage"),

    path("users/", views.user_list, name="user_list"),

    path("check-user/", views.check_user, name="check_user"),

    path("loader/", views.loader, name="api_loader"),

    path("totp-secret/", views.totp_secret, name="api_totp_secret"),

    # ==========================================================================
    # Public Endpoints - No Authentication Required
    # ==========================================================================

    # CSS file listing with pagination, sorting, filtering
    path("css/", views.get_all_css, name="get_all_css"),

    # Search endpoint
    path("css/search/", views.search_css, name="search_css"),

    # Discovery endpoints (must appear before css/<uuid:css_id>/)
    path("css/trending/", views.trending_css, name="api_css_trending"),
    path("css/new/", views.new_css, name="api_css_new"),
    path("css/marketplace-stats/", views.marketplace_stats, name="api_css_marketplace_stats"),

    # Categories
    path("categories/", views.list_categories, name="list_categories"),

    # Get specific CSS file by ID
    path("css/<uuid:css_id>/", views.get_one_css, name="get_one_css"),

    # ==========================================================================
    # Authenticated Endpoints - CRUD Operations
    # ==========================================================================

    # Create new CSS file
    path("css/create/", views.create_css, name="create_css"),

    # Update CSS file (owner only)
    path("css/<uuid:css_id>/update/", views.update_css, name="update_css"),

    # Delete CSS file (owner only)
    path("css/<uuid:css_id>/delete/", views.delete_css, name="delete_css"),

    # ==========================================================================
    # Authenticated Endpoints - User's CSS Collections
    # ==========================================================================

    # Get user's own CSS files
    path("css/my/", views.get_my_css, name="get_my_css"),

    # Get user's purchased CSS files
    path("css/purchased/", views.get_purchased_css, name="get_purchased_css"),

    # Get all accessible CSS (owned + purchased)
    path("css/accessible/", views.get_accessible_css, name="get_accessible_css"),

    # ==========================================================================
    # Authenticated Endpoints - Commerce
    # ==========================================================================

    # Purchase a CSS file
    path("css/<uuid:css_id>/purchase/", views.purchase_css, name="purchase_css"),

    # Download/log access to CSS file (owned or purchased)
    path("css/<uuid:css_id>/download/", views.download_css, name="download_css"),

    # ==========================================================================
    # Authenticated Endpoints - Analytics
    # ==========================================================================

    # Seller analytics dashboard
    path("analytics/", views.seller_analytics, name="seller_analytics"),

    # ==========================================================================
    # Legacy Endpoints (for backwards compatibility)
    # ==========================================================================

    # Legacy list endpoint without new response format
    path("css/legacy/", views.legacy_get_all_css, name="legacy_get_all_css"),

    # ==========================================================================
    # Mission Board API Endpoints
    # ==========================================================================

    # List all missions / Create a new mission
    path("missions/", views.mission_api_list, name="mission_api_list"),

    # Search missions
    path("missions/search/", views.mission_api_search, name="mission_api_search"),

    # Export missions (JSON/CSV)
    path("missions/export/", views.mission_api_export, name="mission_api_export"),

    # Get, update, or delete a specific mission
    path("missions/<int:mission_id>/", views.mission_api_detail, name="mission_api_detail"),

    # ==========================================================================
    # Moderation API Endpoints (staff only)
    # ==========================================================================

    # Dashboard
    path("moderation/dashboard/", views_moderation.dashboard_view, name="api_moderation_dashboard"),

    # Reports
    path("moderation/reports/", views_moderation.reports_view, name="api_moderation_reports"),
    path("moderation/reports/<uuid:pk>/", views_moderation.report_detail_view, name="api_moderation_report_detail"),
    path("moderation/reports/<uuid:pk>/resolve/", views_moderation.report_resolve_view, name="api_moderation_report_resolve"),
    path("moderation/reports/<uuid:pk>/assign/", views_moderation.report_assign_view, name="api_moderation_report_assign"),
    path("moderation/reports/<uuid:pk>/note/", views_moderation.report_note_view, name="api_moderation_report_note"),

    # Content queue
    path("moderation/content/queue/", views_moderation.content_queue_view, name="api_moderation_content_queue"),
    path("moderation/content/<str:pk>/", views_moderation.content_review_view, name="api_moderation_content_review"),
    path("moderation/content/<str:pk>/action/", views_moderation.content_action_view, name="api_moderation_content_action"),
    path("moderation/content/history/", views_moderation.content_history_view, name="api_moderation_content_history"),

    # Sanctions — user overview
    path("moderation/user/<str:username>/", views_moderation.user_overview_view, name="api_moderation_user_overview"),
    path("moderation/user/<str:username>/warning/", views_moderation.issue_warning_view, name="api_moderation_issue_warning"),
    path("moderation/user/<str:username>/mute/", views_moderation.mute_user_view, name="api_moderation_mute_user"),
    path("moderation/user/<str:username>/ban/", views_moderation.ban_user_view, name="api_moderation_ban_user"),
    path("moderation/mute/<uuid:pk>/lift/", views_moderation.lift_mute_view, name="api_moderation_lift_mute"),
    path("moderation/ban/<uuid:pk>/lift/", views_moderation.lift_ban_view, name="api_moderation_lift_ban"),

    # Appeals
    path("moderation/appeals/", views_moderation.appeals_view, name="api_moderation_appeals"),
    path("moderation/appeals/<uuid:pk>/", views_moderation.appeal_review_view, name="api_moderation_appeal_review"),

    # Audit log
    path("moderation/audit/", views_moderation.audit_log_view, name="api_moderation_audit_log"),

    # Staff management
    path("moderation/staff/", views_moderation.staff_list_view, name="api_moderation_staff_list"),
    path("moderation/staff/<int:user_id>/assign/", views_moderation.staff_assign_role_view, name="api_moderation_staff_assign"),

    # Auto-mod rules
    path("moderation/automod/rules/", views_moderation.automod_rules_view, name="api_moderation_automod_rules"),
    path("moderation/automod/rules/create/", views_moderation.automod_rule_create_view, name="api_moderation_automod_rule_create"),
    path("moderation/automod/rules/<uuid:pk>/", views_moderation.automod_rule_detail_view, name="api_moderation_automod_rule_detail"),
    path("moderation/automod/logs/", views_moderation.automod_logs_view, name="api_moderation_automod_logs"),
]
