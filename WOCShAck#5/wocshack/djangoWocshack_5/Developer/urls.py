"""
Developer module URL configuration.
"""
from django.urls import path
from django.views.generic import RedirectView

from . import views, views_editor, views_publishing, views_analytics
from . import views_webhooks, views_payouts, views_tools, views_docs, views_coupons
from . import views_admin

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='developer_dashboard'),
    path('profile/', views.developer_profile, name='developer_profile'),
    path('profile/edit/', views.edit_developer_profile, name='edit_developer_profile'),

    # Subscription
    path('subscribe/', views.subscribe, name='developer_subscribe'),
    path('subscribe/checkout/', views.subscription_checkout, name='developer_subscription_checkout'),
    path('subscribe/<slug:plan_slug>/', views.subscribe_to_plan, name='developer_subscribe_plan'),
    path('subscription/', views.subscription_status, name='developer_subscription'),
    path('subscription/cancel/', views.cancel_subscription, name='developer_cancel_subscription'),

    # Editor & Projects
    path('editor/', views_editor.editor, name='developer_editor'),
    path('projects/', views_editor.project_list, name='developer_projects'),
    path('projects/create/', views_editor.create_project, name='developer_create_project'),
    path('projects/<uuid:project_id>/', views_editor.edit_project, name='developer_edit_project'),
    path('projects/<uuid:project_id>/save/', views_editor.save_project, name='developer_save_project'),
    path('projects/<uuid:project_id>/delete/', views_editor.delete_project, name='developer_delete_project'),
    path('projects/<uuid:project_id>/versions/', views_editor.version_list, name='developer_versions'),
    path('projects/<uuid:project_id>/version/', views_editor.create_version, name='developer_create_version'),
    path('templates/', views_editor.template_list, name='developer_templates'),
    path('css/<uuid:css_id>/save/', views_editor.save_api_css, name='developer_save_api_css'),

    # Publishing & Listings
    path('publish/<uuid:project_id>/', views_publishing.publish_project, name='developer_publish'),
    path('listings/', views_publishing.listing_list, name='developer_listings'),
    path('listings/<uuid:listing_id>/', views_publishing.edit_listing, name='developer_edit_listing'),
    path('listings/<uuid:listing_id>/delete/', views_publishing.delete_listing, name='developer_delete_listing'),
    path('listings/<uuid:listing_id>/pricing/', views_publishing.set_pricing, name='developer_set_pricing'),
    path('promotions/', views_publishing.promotion_list, name='developer_promotions'),
    path('promotions/create/', views_publishing.create_promotion, name='developer_create_promotion'),

    # E-shop coupons
    path('coupons/', views_coupons.coupon_list, name='developer_coupons'),
    path('coupons/create/', views_coupons.create_coupon, name='developer_create_coupon'),
    path('coupons/<uuid:coupon_id>/delete/', views_coupons.delete_coupon, name='developer_delete_coupon'),

    # Analytics
    path('analytics/', views_analytics.analytics_dashboard, name='developer_analytics'),
    path('analytics/revenue/', views_analytics.revenue_analytics, name='developer_revenue_analytics'),
    path('analytics/products/', views_analytics.product_analytics, name='developer_product_analytics'),
    path('analytics/customers/', views_analytics.customer_analytics, name='developer_customer_analytics'),
    path('analytics/export/', views_analytics.export_analytics, name='developer_export_analytics'),

    # API Keys (redirected to unified Api module)
    path('api-keys/', RedirectView.as_view(url='/api/keys/', permanent=True), name='developer_api_keys'),

    # Webhooks
    path('webhooks/', views_webhooks.webhook_list, name='developer_webhooks'),
    path('webhooks/create/', views_webhooks.create_webhook, name='developer_create_webhook'),
    path('webhooks/<uuid:webhook_id>/edit/', views_webhooks.edit_webhook, name='developer_edit_webhook'),
    path('webhooks/<uuid:webhook_id>/delete/', views_webhooks.delete_webhook, name='developer_delete_webhook'),
    path('webhooks/<uuid:webhook_id>/logs/', views_webhooks.webhook_logs, name='developer_webhook_logs'),
    path('webhooks/<uuid:webhook_id>/test/', views_webhooks.test_webhook, name='developer_test_webhook'),

    # Payouts
    path('payouts/', views_payouts.payout_dashboard, name='developer_payouts'),
    path('payouts/request/', views_payouts.request_payout, name='developer_request_payout'),
    path('payouts/history/', views_payouts.payout_history, name='developer_payout_history'),

    # Tools
    path('tools/', views_tools.tools_page, name='developer_tools'),
    path('tools/minify/', views_tools.minify_css_view, name='developer_minify'),
    path('tools/beautify/', views_tools.beautify_css_view, name='developer_beautify'),
    path('tools/validate/', views_tools.validate_css_view, name='developer_validate'),
    path('tools/prefix/', views_tools.prefix_css_view, name='developer_prefix'),

    # Documentation
    path('docs/', views_docs.docs_home, name='developer_docs'),
    path('docs/api/', views_docs.docs_api, name='developer_docs_api'),
    path('docs/webhooks/', views_docs.docs_webhooks, name='developer_docs_webhooks'),
    path('docs/examples/', views_docs.docs_examples, name='developer_docs_examples'),

    # Staff Admin Panel
    path('admin/', views_admin.admin_dashboard, name='developer_admin_dashboard'),
    path('admin/payouts/', views_admin.payout_list, name='developer_admin_payout_list'),
    path('admin/payouts/<uuid:payout_id>/', views_admin.payout_review, name='developer_admin_payout_review'),
    path('admin/listings/', views_admin.listing_list, name='developer_admin_listing_list'),
    path('admin/listings/<uuid:listing_id>/suspend/', views_admin.listing_suspend, name='developer_admin_listing_suspend'),
    path('admin/subscriptions/', views_admin.subscription_list, name='developer_admin_subscription_list'),
    path('admin/developers/', views_admin.developer_list, name='developer_admin_developer_list'),
    path('admin/plans/', views_admin.plan_list, name='developer_admin_plan_list'),
    path('admin/plans/new/', views_admin.plan_create, name='developer_admin_plan_create'),
    path('admin/plans/<uuid:plan_id>/edit/', views_admin.plan_edit, name='developer_admin_plan_edit'),
    path('admin/promotions/', views_admin.promotion_list, name='developer_admin_promotion_list'),
    path('admin/promotions/<uuid:promotion_id>/revoke/', views_admin.promotion_revoke, name='developer_admin_promotion_revoke'),
    path('admin/coupons/<uuid:coupon_id>/revoke/', views_admin.coupon_revoke, name='developer_admin_coupon_revoke'),
    path('admin/projects/', views_admin.project_list, name='developer_admin_project_list'),
]
