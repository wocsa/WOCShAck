from django.urls import path
from . import views, views_content, views_sanctions, views_admin

app_name = 'admin_panel'

urlpatterns = [
    # Main dashboard and reports
    path('', views.moderation_dashboard, name='dashboard'),
    path('reports/', views.report_list, name='report_list'),
    path('reports/<uuid:pk>/', views.report_detail, name='report_detail'),
    path('reports/<uuid:pk>/resolve/', views.report_resolve, name='report_resolve'),
    path('reports/<uuid:pk>/assign/', views.report_assign, name='report_assign'),
    path('reports/<uuid:pk>/note/', views.add_report_note, name='add_report_note'),

    # Content moderation
    path('content/queue/', views_content.content_queue, name='content_queue'),
    path('content/review/<uuid:pk>/', views_content.content_review, name='content_review'),
    path('content/action/<uuid:pk>/', views_content.content_action, name='content_action'),
    path('content/history/', views_content.content_action_history, name='content_action_history'),

    # User sanctions
    path('user/<str:username>/', views_sanctions.user_overview, name='user_overview'),
    path('user/<str:username>/warning/', views_sanctions.issue_warning, name='issue_warning'),
    path('user/<str:username>/mute/', views_sanctions.mute_user, name='mute_user'),
    path('user/<str:username>/ban/', views_sanctions.ban_user, name='ban_user'),
    path('mute/<uuid:pk>/lift/', views_sanctions.lift_mute, name='lift_mute'),
    path('ban/<uuid:pk>/lift/', views_sanctions.lift_ban, name='lift_ban'),

    # Appeals
    path('appeals/', views_sanctions.appeal_list, name='appeal_list'),
    path('appeals/<uuid:pk>/', views_sanctions.appeal_review, name='appeal_review'),

    # Admin tools
    path('audit/', views_admin.audit_log, name='audit_log'),
    path('staff/', views_admin.staff_list, name='staff_list'),
    path('staff/promote/', views_admin.staff_promote, name='staff_promote'),
    path('staff/user-search/', views_admin.staff_user_search, name='staff_user_search'),
    path('staff/<int:user_id>/assign/', views_admin.staff_assign_role, name='staff_assign_role'),
    path('staff/<int:user_id>/remove/', views_admin.staff_remove, name='staff_remove'),
    path('staff/<int:user_id>/toggle-staff/', views_admin.staff_toggle, name='staff_toggle'),

    path('automod/rules/', views_admin.automod_rules, name='automod_rules'),
    path('automod/rules/<str:pk>/edit/', views_admin.automod_rule_edit, name='automod_rule_edit'),
    path('automod/logs/', views_admin.automod_logs, name='automod_logs'),
]
