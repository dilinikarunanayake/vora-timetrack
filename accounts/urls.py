"""
Sign-in, sign-out and password change, using Django's built-in auth views.
Django handles password hashing, sessions and CSRF protection for us.
"""

from django.contrib.auth import views as auth_views
from django.urls import path

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),  # POST only
    path("password/", auth_views.PasswordChangeView.as_view(), name="password_change"),
    path("password/done/", auth_views.PasswordChangeDoneView.as_view(), name="password_change_done"),
]
