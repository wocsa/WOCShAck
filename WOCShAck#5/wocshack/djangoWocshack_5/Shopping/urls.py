"""
URL configuration for Shopping module.
All routes use proper URL patterns with type validation.
"""
from django.urls import path
from . import views
from . import views_moderation as views_mod

urlpatterns = [
    # -------------------------------------------------------------------------
    # Moderation (staff only)
    # -------------------------------------------------------------------------
    path('admin/', views_mod.moderation_dashboard, name='shop_admin_dashboard'),
    path('admin/reviews/', views_mod.review_list, name='shop_review_list'),
    path('admin/reviews/<uuid:review_id>/delete/', views_mod.review_delete, name='shop_review_delete'),
    path('admin/orders/', views_mod.order_list, name='shop_order_list'),
    path('admin/orders/<uuid:order_id>/', views_mod.order_detail, name='shop_order_detail'),
    path('admin/orders/<uuid:order_id>/status/', views_mod.order_update_status, name='shop_order_update_status'),
    path('admin/products/', views_mod.product_list, name='shop_product_list'),
    path('admin/products/<uuid:css_id>/toggle/', views_mod.product_toggle_active, name='shop_product_toggle'),


    # Shop listing
    path("", views.shop, name="shop"),
    path("product/<uuid:css_id>/", views.product_detail, name="product_detail"),

    # Cart management
    path("cart/", views.cart, name="cart"),
    path("add/<uuid:css_id>/", views.add_to_cart, name="add_to_cart"),
    path("remove/<uuid:css_id>/", views.remove_from_cart, name="remove_from_cart"),
    path("update/<uuid:css_id>/", views.update_cart, name="update_cart"),
    path("cart/count/", views.cart_count, name="cart_count"),
    path("cart/quick-add/<uuid:css_id>/", views.quick_add_to_cart, name="quick_add_to_cart"),

    # Coupon management
    path("coupon/apply/", views.apply_coupon, name="apply_coupon"),
    path("coupon/remove/", views.remove_coupon, name="remove_coupon"),

    # Payment flow
    path("payment/", views.payment, name="payment"),
    path("payment/loading/", views.payment_loading, name="payment_loading"),
    path("payment/complete/", views.complete_order, name="complete_order"),

    # Order history
    path("orders/", views.order_history, name="order_history"),
    path("orders/<uuid:order_id>/", views.order_detail, name="order_detail"),
    path("orders/<uuid:order_id>/invoice/", views.download_invoice, name="download_invoice"),

    # Reviews
    path("product/<uuid:css_id>/reviews/", views.reviews_page, name="reviews_page"),
    path("product/<uuid:css_id>/review/add/", views.add_review, name="add_review"),
    path("review/<uuid:review_id>/delete/", views.delete_review, name="delete_review"),

    # Wishlist
    path("wishlist/", views.wishlist, name="wishlist"),
    path("wishlist/add/<uuid:css_id>/", views.add_to_wishlist, name="add_to_wishlist"),
    path("wishlist/remove/<uuid:css_id>/", views.remove_from_wishlist, name="remove_from_wishlist"),
    path("wishlist/move-to-cart/<uuid:css_id>/", views.move_to_cart, name="move_to_cart"),

    # Seller profiles
    path("seller/<str:username>/", views.seller_profile, name="seller_profile"),
    path("product/<uuid:css_id>/seller/", views.seller_by_css, name="seller_by_css"),

    # Article management (seller tools)
    path("sell/", views.add_article, name="add_article"),
]
