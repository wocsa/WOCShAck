from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("todos/", views.todos, name="todos"),
    path("terms-of-service/", views.terms_of_service, name="terms_of_service"),
    path("privacy-policy/", views.privacy_policy, name="privacy_policy"),

    # Mission Board — CRUD
    path("todos/missions/", views.mission_list, name="mission_list"),
    path("todos/missions/create/", views.mission_create, name="mission_create"),
    path("todos/missions/<int:mission_id>/", views.mission_detail, name="mission_detail"),
    path("todos/missions/<int:mission_id>/edit/", views.mission_update, name="mission_update"),
    path("todos/missions/<int:mission_id>/delete/", views.mission_delete, name="mission_delete"),
    path("todos/missions/<int:mission_id>/toggle/", views.mission_toggle_status, name="mission_toggle_status"),
]
