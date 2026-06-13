"""
URL configuration for Account module.
All routes use proper URL patterns with type validation.
"""
from django.urls import path
from . import views
from . import views_admin

urlpatterns = [
    # Authentication
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("activate/", views.activate_account, name="activate_account"),
    path("password-reset-request/", views.password_reset_request, name="password_reset_request"),
    path("password_reset/", views.password_reset_form, name="password_reset"),

    # Account dashboard
    path("", views.account, name="account"),
    path("settings/", views.settings, name="settings"),
    path("purchased-articles/", views.purchased_articles, name="purchased_articles"),

    # 2FA - Initial setup during registration flow
    path("verification/", views.verification, name="verification"),
    path("process/", views.process, name="process"),
    path("ask-2fa/", views.ask_2fa, name="ask_2fa"),
    path("ask-2fa/no", views.ask_2fa_no, name="ask_2fa_no"),

    # 2FA Management - Setup and manage from settings
    path("2fa/setup/", views.setup_2fa, name="setup_2fa"),
    path("2fa/manage/", views.manage_2fa, name="manage_2fa"),
    path("2fa/disable/", views.disable_2fa, name="disable_2fa"),

    # Email 2FA
    path("2fa/email/setup/", views.setup_email_2fa, name="setup_email_2fa"),
    path("2fa/email/disable/", views.disable_email_2fa, name="disable_email_2fa"),
    path("2fa/email/verify/", views.email_2fa_verification, name="email_2fa_verify"),

    # Backup codes for 2FA
    path("backup-codes/", views.backup_codes, name="backup_codes"),
    path("backup-codes/generate/", views.generate_backup_codes, name="generate_backup_codes"),
    path("backup-codes/display/", views.backup_codes_display, name="backup_codes_display"),

    # Bank PIN setup
    path("ask-pin/", views.ask_pin, name="ask_pin"),
    path("process/bank/", views.process_bank, name="process_bank"),

    # Login history / Activity log
    path("login-history/", views.login_history, name="login_history"),

    # Session management
    path("sessions/", views.sessions, name="sessions"),
    path("sessions/revoke/<int:session_id>/", views.revoke_session, name="revoke_session"),
    path("sessions/revoke-all/", views.revoke_all_sessions, name="revoke_all_sessions"),

    # Public profile - supports both query param (?username=x) and path param
    path("profile/", views.public_profile, name="public_profile"),
    path("profile/<str:username>/", views.public_profile, name="public_profile_by_username"),

    # Premium Store
    path("store/", views.store, name="store"),
    path("store/purchase/<str:feature_type>/", views.store_purchase, name="store_purchase"),
    path("store/payment_loading/", views.store_payment_loading, name="store_payment_loading"),
    path("store/complete_order/", views.store_complete_order, name="store_complete_order"),
    path("store/customize-theme/", views.customize_theme, name="customize_theme"),

    # Admin panel (staff only)
    path("admin/", views_admin.admin_dashboard, name="account_admin_dashboard"),
    path("admin/users/", views_admin.user_list, name="account_admin_user_list"),
    path("admin/users/<int:user_id>/", views_admin.user_detail, name="account_admin_user_detail"),
    path("admin/users/<int:user_id>/suspend/", views_admin.user_suspend, name="account_admin_user_suspend"),
    path("admin/users/<int:user_id>/unsuspend/", views_admin.user_unsuspend, name="account_admin_user_unsuspend"),
    path("admin/users/<int:user_id>/promote/", views_admin.user_promote, name="account_admin_user_promote"),
    path("admin/users/<int:user_id>/demote/", views_admin.user_demote, name="account_admin_user_demote"),
    path("admin/verification/", views_admin.verification_list, name="account_admin_verification"),
]
