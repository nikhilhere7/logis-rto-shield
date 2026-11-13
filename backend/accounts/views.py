from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from core.models import Merchant, User


def describe(user):
    """The public view of a user. Never includes the password hash or staff flags."""
    return {
        "name": user.first_name or user.username,
        "email": user.email,
        "merchant": user.merchant.name if user.merchant_id else None,
    }


def session(user):
    """What the frontend needs after signing up or logging in."""
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": describe(user),
    }


class SignupInput(serializers.Serializer):
    business_name = serializers.CharField(max_length=120)
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_business_name(self, value):
        value = " ".join(value.split())
        if Merchant.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError("A business with this name is already registered.")
        return value

    def validate_email(self, value):
        value = value.strip().lower()
        if (
            User.objects.filter(username__iexact=value).exists()
            or User.objects.filter(email__iexact=value).exclude(email="").exists()
        ):
            raise serializers.ValidationError("An account with this email already exists. Log in instead.")
        return value

    def validate_password(self, value):
        validate_password(value)  # Django's rules: length, not too common, not all digits
        return value


class SignupView(APIView):
    """Anyone can register. One call creates the merchant and its first user together."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "signup"

    def post(self, request):
        form = SignupInput(data=request.data)
        form.is_valid(raise_exception=True)
        d = form.validated_data
        with transaction.atomic():
            merchant = Merchant.objects.create(name=d["business_name"])
            user = User.objects.create_user(
                username=d["email"],
                email=d["email"],
                password=d["password"],
                first_name=d["name"].strip(),
                merchant=merchant,
            )
        return Response(session(user), status=status.HTTP_201_CREATED)


class LoginView(TokenObtainPairView):
    """POST {"email": ..., "password": ...} -> access and refresh tokens plus the user.
    Accounts made in Django admin have a plain username, so that is accepted in the same field."""
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request, *args, **kwargs):
        typed = str(request.data.get("email") or request.data.get("username") or "").strip()
        match = (
            User.objects.filter(username__iexact=typed).first()
            or User.objects.filter(email__iexact=typed).exclude(email="").first()
        )
        serializer = self.get_serializer(data={
            "username": match.username if match else typed,
            "password": request.data.get("password", ""),
        })
        serializer.is_valid(raise_exception=True)
        return Response({**serializer.validated_data, "user": describe(serializer.user)})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(describe(request.user))
