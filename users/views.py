from django.contrib.auth.views import PasswordChangeView
from django.views.generic import FormView, DetailView, UpdateView
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.shortcuts import redirect, reverse
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.core.files.base import ContentFile
from users.forms import LoginForm, SignUpForm
from users.mixins import LoggedOutOnlyView, LoggedInOnlyView, EmailLoginOnlyView
from users.models import User

import os
import requests


class LoginView(LoggedOutOnlyView, FormView):
    """users application LoginView class

    Inherit       : LoggedOutOnlyView, FormView
    template_name : "users/login.html"
    form_class    : LoginForm
    success_url   : reverse_lazy("core:home")

    Method:
        form_valid : user auth process
    """

    template_name = "users/login.html"
    form_class = LoginForm

    def form_valid(self, form):
        email = form.cleaned_data.get("email")
        password = form.cleaned_data.get("password")

        user = authenticate(self.request, username=email, password=password)

        if user is not None:
            login(self.request, user)

        return super().form_valid(form)

    def get_success_url(self):
        next_arg = self.request.GET.get("next")
        if next_arg:
            return next_arg
        return reverse("core:home")


def log_out(request):
    messages.info(request, "See you later")
    logout(request)

    return redirect(reverse("core:home"))


class SignUpView(LoggedOutOnlyView, FormView):
    """users application SignUpView class

    Inherit       : LoggedOutOnlyView, FormView
    template_name : users/signup.html
    form_class    : SignUpForm
    success_url   : reverse_lazy("core:home")

    Method:
        form_valid : Create user using save method and login user
    """

    template_name = "users/signup.html"
    form_class = SignUpForm
    success_url = reverse_lazy("core:home")

    def form_valid(self, form):
        form.save()
        email = form.cleaned_data.get("email")
        password = form.cleaned_data.get("password")

        user = authenticate(self.request, username=email, password=password)

        if user is not None:
            login(self.request, user)
        user.verify_email()
        return super().form_valid(form)


def complete_verification(request, key):
    try:
        user = User.objects.get(email_secret=key)
        user.email_verified = True
        user.email_secret = ""
        user.save()
        # To do : add success message
    except User.DoesNotExist:
        # To do : add error message
        pass

    return redirect(reverse("core:home"))


def github_login(request):
    client_id = os.environ.get("GITHUB_CLIENT_ID")

    redirect_url = "http://127.0.0.1:8000/users/login/github/callback"
    query_string = (
        f"?client_id={client_id}" + f"&redirect_url={redirect_url}" + "&scope=read:user"
    )
    return redirect("https://github.com/login/oauth/authorize" + query_string)


class GithubException(Exception):
    pass


def github_callback(request):
    try:
        code = request.GET.get("code", None)
        client_id = os.environ.get("GITHUB_CLIENT_ID")
        client_secret = os.environ.get("GITHUB_CLIENT_SECRET")

        if code is not None:
            token_response = requests.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                },
                headers={"Accept": "application/json"},
            )
            token_json = token_response.json()
            error = token_json.get("error", None)

            if error:
                raise GithubException("Can't get access token")

            access_token = token_json.get("access_token")
            profile_response = requests.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"token {access_token}",
                    "Accept": "application/json",
                },
            )
            profile_json = profile_response.json()
            username = profile_json.get("login", None)

            if not username:
                raise GithubException("Can't get your profile")

            name = profile_json.get("name")
            email = profile_json.get("email")
            bio = profile_json.get("bio")
            avatar_url = profile_json.get("avatar_url", None)

            try:
                user = User.objects.get(email=email)

                if user.login_method != User.LOGIN_GITHUB:
                    raise GithubException(f"Please login with: {user.login_method}")

            except User.DoesNotExist:
                user = User.objects.create(
                    username=email,
                    first_name=name,
                    bio=bio,
                    email=email,
                    email_verified=True,
                    login_method=User.LOGIN_GITHUB,
                )
                user.set_unusable_password()
                user.save()

                if avatar_url:
                    photo_response = requests.get(avatar_url)
                    user.avatar.save(
                        f"pk-{user.pk}-{name}-avatar",
                        ContentFile(photo_response.content),
                    )

            login(request, user)
            messages.success(request, f"Welcome back {user.first_name}")

            return redirect(reverse("core:home"))

        raise GithubException()
    except GithubException as e:
        messages.error(request, e)
        return redirect(reverse("users:login"))


def kakao_login(request):
    client_id = os.environ.get("KAKAO_API_KEY")
    redirect_uri = "http://127.0.0.1:8000/users/login/kakao/callback"
    kakao_url = "https://kauth.kakao.com/oauth/authorize"
    query_string = (
        f"?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code"
    )

    return redirect(kakao_url + query_string)


class KakaoException(Exception):
    pass


def kakao_callback(request):
    try:
        code = request.GET.get("code", None)

        if not code:
            raise KakaoException("Can't get authorization code.")

        client_id = os.environ.get("KAKAO_API_KEY")
        redirect_uri = "http://127.0.0.1:8000/users/login/kakao/callback"
        data = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code": code,
        }
        token_response = requests.post("https://kauth.kakao.com/oauth/token", data=data)
        token_json = token_response.json()
        error = token_json.get("error", None)

        if error:
            raise KakaoException("Can't get authorization code.")

        access_token = token_json.get("access_token")
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-type": "application/x-www-form-urlencoded;charset=utf-8",
        }
        profile_response = requests.get(
            "https://kapi.kakao.com/v2/user/me", headers=headers
        )

        profile_json = profile_response.json()
        email = profile_json.get("kakao_account").get("email", None)

        if not email:
            raise KakaoException("Please also give me your email")

        properties = profile_json.get("properties")
        nickname = properties.get("nickname")
        profile_image = properties.get("profile_image", None)

        try:
            user = User.objects.get(email=email)

            if user.login_method != User.LOGIN_KAKAO:
                raise KakaoException(f"Please login with: {user.login_method}")

        except User.DoesNotExist:
            user = User.objects.create(
                username=email,
                first_name=nickname,
                email=email,
                email_verified=True,
                login_method=User.LOGIN_KAKAO,
            )
            user.set_unusable_password()
            user.save()

            if profile_image:
                photo_response = requests.get(profile_image)
                user.avatar.save(
                    f"pk-{user.pk}-{nickname}-avatar",
                    ContentFile(photo_response.content),
                )

        messages.success(request, f"Welcome back {user.first_name}")
        login(request, user)

        return redirect(reverse("core:home"))
    except KakaoException as e:
        messages.error(request, e)
        return redirect(reverse("users:login"))


class UserProfileView(LoggedInOnlyView, DetailView):
    """users application UserProfileView class

    Inherit       :  DetailView
    template_name : "users/user_detail.html"
    """

    model = User
    context_object_name = "user_obj"


class UpdateProfileView(LoggedInOnlyView, SuccessMessageMixin, UpdateView):
    """users application UpdateProfileView class

    Inherit       : SuccessMessageMixin, UpdateView
    template_name : "users/update_profile.html"
    """

    model = User
    template_name = "users/update_profile.html"
    fields = (
        "first_name",
        "last_name",
        "gender",
        "bio",
        "birth_date",
        "language",
        "currency",
    )
    success_message = "Profile Updated"

    def get_object(self, queryset=None):
        return self.request.user

    def get_form(self, form_class=None):
        form = super().get_form(form_class=form_class)
        form.fields["first_name"].widget.attrs = {"placeholder": "First name"}
        form.fields["last_name"].widget.attrs = {"placeholder": "Last name"}
        form.fields["bio"].widget.attrs = {"placeholder": "Bio"}
        form.fields["birth_date"].widget.attrs = {"placeholder": "Birthdate"}
        return form


class UpdatePasswordView(
    EmailLoginOnlyView, LoggedInOnlyView, SuccessMessageMixin, PasswordChangeView
):
    """users application UpdatePasswordView class

    Inherit       : PasswordChangeView
    template_name : "users/update_password.html"
    """

    template_name = "users/update_password.html"
    success_message = "Password Updated"

    def get_form(self, form_class=None):
        form = super().get_form(form_class=form_class)
        form.fields["old_password"].widget.attrs = {"placeholder": "Current password"}
        form.fields["new_password1"].widget.attrs = {"placeholder": "New password"}
        form.fields["new_password2"].widget.attrs = {
            "placeholder": "Confirm new password"
        }
        return form

    def get_success_url(self):
        return self.request.user.get_absolute_url()
