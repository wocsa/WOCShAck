from django.urls import path
from . import views

urlpatterns = [
    # Public landing
    path('', views.advertisement_index, name='advertisement_index'),

    # Advertiser self-service
    path('create/', views.create_advertisement, name='create_advertisement'),
    path('dashboard/', views.advertiser_dashboard, name='advertiser_dashboard'),
    path('<uuid:ad_id>/', views.advertisement_detail, name='advertisement_detail'),
    path('<uuid:ad_id>/edit/', views.edit_advertisement, name='edit_advertisement'),
    path('<uuid:ad_id>/activate/', views.activate_ad, name='activate_ad'),
    path('stats/<uuid:ad_id>/', views.ad_stats, name='ad_stats'),

    # Image reorder (AJAX)
    path('<uuid:ad_id>/reorder-images/', views.reorder_images, name='reorder_images'),

    # Click tracking
    path('click/<uuid:ad_id>/', views.record_click, name='record_click'),

    path('preview/', views.ad_preview, name='ad_preview'),

    # Staff admin
    path('admin/pending/', views.admin_pending_ads, name='admin_pending_ads'),
    path('admin/approve/<uuid:ad_id>/', views.approve_ad, name='approve_ad'),
    path('admin/reject/<uuid:ad_id>/', views.reject_ad, name='reject_ad'),

    # Extended admin panel
    path('admin/dashboard/', views.admin_dashboard, name='advertisement_admin_dashboard'),
    path('admin/all/', views.admin_all_ads, name='advertisement_admin_all'),
    path('admin/suspend/<uuid:ad_id>/', views.admin_suspend_ad, name='advertisement_admin_suspend'),
    path('admin/unsuspend/<uuid:ad_id>/', views.admin_unsuspend_ad, name='advertisement_admin_unsuspend'),
]
