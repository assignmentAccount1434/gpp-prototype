from django.urls import path
from . import views

urlpatterns = [
    path("", views.app, name="app"),
    path("signup/", views.signup, name="signup"),
    path("signin/", views.signin, name="signin"),

    path("api/bootstrap/", views.bootstrap),
    path("api/keys/", views.publish_key),
    path("api/keys/<int:key_id>/retire/", views.retire_key),
    path("api/submit/", views.submit),
    path("api/submissions/", views.submissions),
    path(
        "api/submissions/<uuid:submission_id>/delete/",
        views.delete_submission,
    ),
    path("api/access/<int:access_id>/revoke/", views.revoke_access),
    path(
        "api/submissions/<uuid:submission_id>/contact/",
        views.request_contact,
    ),
    path("api/contacts/", views.contacts),
    path(
        "api/contacts/<int:contact_id>/respond/",
        views.respond_contact,
    ),
]
