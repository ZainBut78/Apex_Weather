import logging

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from django.conf import settings
from drf_spectacular.utils import extend_schema

from .models import APICustomer, APIKey
from .utils import create_and_send_otp, verify_otp

logger = logging.getLogger(__name__)


def issue_tokens(user):
    refresh = RefreshToken.for_user(user)
    return {"access_token": str(refresh.access_token), "refresh_token": str(refresh)}


@extend_schema(
    request={"application/json": {"type": "object", "properties": {
        "username": {"type": "string"}, "email": {"type": "string", "format": "email"},
        "password": {"type": "string", "minLength": 8}, "company_name": {"type": "string"}
    }, "required": ["username", "email", "password"]}},
    responses={201: {"type": "object", "properties": {"message": {"type": "string"}, "email": {"type": "string"}}},
               400: {"type": "object", "properties": {"error": {"type": "string"}}}},
    description="Register new account. OTP sent to email for verification.",
)
@api_view(['POST'])
@permission_classes([AllowAny])
def register_request(request):
    username = request.data.get("username", "").strip()
    email = request.data.get("email", "").strip().lower()
    password = request.data.get("password", "")
    company_name = request.data.get("company_name", "")

    if not username or not email or not password:
        return Response({"error": "username, email and password required"}, status=400)
    if len(password) < 8:
        return Response({"error": "Password must be at least 8 characters"}, status=400)
    # settings.AUTH_PASSWORD_VALIDATORS configured thay magar register pe
    # kabhi run nahi hote thay — "password" / "12345678" jaise passwords
    # aaraam se accept ho jate thay. Ab actually enforce hote hain.
    try:
        validate_password(password)
    except DjangoValidationError as exc:
        return Response({"error": exc.messages[0], "all_errors": list(exc.messages)}, status=400)
    if User.objects.filter(username=username).exists():
        return Response({"error": "Username already taken."}, status=400)
    if User.objects.filter(email=email).exists():
        return Response({"error": "Account already exists with this email. Please login."}, status=400)

    user = User.objects.create_user(username=username, email=email, password=password)
    user.is_active = False
    user.save()
    APICustomer.objects.create(user=user, company_name=company_name, plan="free")

    # Agar SMTP down ho to pehle 500 aata tha aur inactive user row DB
    # mein reh jati thi — us email/username se dobara register karna
    # hamesha ke liye block ho jata tha. Ab rollback karke 503 dete hain.
    try:
        create_and_send_otp(email, "register")
    except Exception:
        logger.exception("Registration OTP email bhejne mein fail: %s", email)
        user.delete()   # APICustomer bhi cascade se delete ho jayega
        return Response(
            {"error": "Could not send verification email. Please try again shortly."},
            status=503,
        )

    return Response({
        "message": "OTP sent to your email. Verify to complete registration.",
        "email": email,
    }, status=201)


@extend_schema(
    request={"application/json": {"type": "object", "properties": {
        "email": {"type": "string", "format": "email"}, "otp": {"type": "string"}
    }, "required": ["email", "otp"]}},
    responses={200: {"type": "object", "properties": {
        "access_token": {"type": "string"}, "refresh_token": {"type": "string"}, "plan": {"type": "string"}
    }}},
    description="Verify OTP to complete registration.",
)
@api_view(['POST'])
@permission_classes([AllowAny])
def verify_registration_otp(request):
    email = request.data.get("email", "").strip().lower()
    otp_code = request.data.get("otp", "").strip()

    if not email or not otp_code:
        return Response({"error": "email and otp required"}, status=400)

    is_valid, message = verify_otp(email, otp_code, "register")
    if not is_valid:
        return Response({"error": message}, status=400)

    # .get() ki jagah .filter().first() — duplicate email pe
    # MultipleObjectsReturned se 500 aa raha tha.
    user = User.objects.filter(email=email).order_by("id").first()
    if user is None:
        return Response({"error": "User not found"}, status=404)

    user.is_active = True
    user.save(update_fields=["is_active"])

    tokens = issue_tokens(user)
    tokens["plan"] = "free"
    return Response(tokens, status=200)


@extend_schema(
    request={"application/json": {"type": "object", "properties": {
        "email": {"type": "string", "description": "Email or username"},
        "password": {"type": "string"}
    }, "required": ["email", "password"]}},
    responses={200: {"type": "object", "properties": {
        "access_token": {"type": "string"}, "refresh_token": {"type": "string"},
        "username": {"type": "string"}, "plan": {"type": "string"}
    }}},
    description="Login with email/username and password.",
)
@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    login_id = request.data.get("email", "").strip()
    password = request.data.get("password", "")

    if not login_id or not password:
        return Response({"error": "email/username and password required"}, status=400)

    user = None
    if "@" in login_id:
        # .get() duplicate email pe MultipleObjectsReturned phenk kar 500
        # deta tha (Django ka User.email unique nahi hota).
        user = User.objects.filter(email=login_id.lower()).order_by("id").first()
    if user is None:
        user = authenticate(username=login_id, password=password)
    else:
        user = authenticate(username=user.username, password=password)
    if user is None:
        return Response({"error": "Invalid email/username or password"}, status=401)
    if not user.is_active:
        return Response({"error": "Account not verified. Please complete OTP verification."}, status=403)

    tokens = issue_tokens(user)
    tokens["username"] = user.username
    try:
        tokens["plan"] = user.apicustomer.plan
    except APICustomer.DoesNotExist:
        tokens["plan"] = None
    return Response(tokens, status=200)


@extend_schema(
    request={"application/json": {"type": "object", "properties": {
        "email": {"type": "string", "format": "email"}
    }, "required": ["email"]}},
    responses={200: {"type": "object", "properties": {"message": {"type": "string"}}}},
    description="Request password reset OTP. Always returns success for security.",
)
@api_view(['POST'])
@permission_classes([AllowAny])
def forgot_password_request(request):
    email = request.data.get("email", "").strip().lower()
    if User.objects.filter(email=email).exists():
        create_and_send_otp(email, "password_reset")
    return Response({"message": "If this email exists, an OTP has been sent."}, status=200)


@extend_schema(
    request={"application/json": {"type": "object", "properties": {
        "email": {"type": "string", "format": "email"}, "otp": {"type": "string"},
        "new_password": {"type": "string", "minLength": 8}
    }, "required": ["email", "otp", "new_password"]}},
    responses={200: {"type": "object", "properties": {"message": {"type": "string"}}}},
    description="Confirm password reset with OTP and set new password.",
)
@api_view(['POST'])
@permission_classes([AllowAny])
def forgot_password_confirm(request):
    email = request.data.get("email", "").strip().lower()
    otp_code = request.data.get("otp", "").strip()
    new_password = request.data.get("new_password", "")

    if len(new_password) < 8:
        return Response({"error": "Password must be at least 8 characters"}, status=400)
    # Password reset pe bhi wahi validators lagao.
    try:
        validate_password(new_password)
    except DjangoValidationError as exc:
        return Response({"error": exc.messages[0], "all_errors": list(exc.messages)}, status=400)

    is_valid, message = verify_otp(email, otp_code, "password_reset")
    if not is_valid:
        return Response({"error": message}, status=400)

    user = User.objects.filter(email=email).order_by("id").first()
    if user is None:
        return Response({"error": "User not found"}, status=404)

    user.set_password(new_password)
    user.save(update_fields=["password"])

    return Response({"message": "Password reset successful. Please login."}, status=200)


@extend_schema(
    request={"application/json": {"type": "object", "properties": {
        "id_token": {"type": "string", "description": "Google OAuth ID token"}
    }, "required": ["id_token"]}},
    responses={200: {"type": "object", "properties": {
        "access_token": {"type": "string"}, "refresh_token": {"type": "string"}, "plan": {"type": "string"}
    }}},
    description="Continue with Google. Creates account if new user.",
)
@api_view(['POST'])
@permission_classes([AllowAny])
def google_login(request):
    google_token = request.data.get("id_token", "")
    if not google_token:
        return Response({"error": "id_token required"}, status=400)

    try:
        idinfo = id_token.verify_oauth2_token(
            google_token, google_requests.Request(), settings.GOOGLE_OAUTH_CLIENT_ID
        )
    except ValueError:
        return Response({"error": "Invalid Google token"}, status=401)

    email = idinfo.get("email")
    if not email:
        return Response({"error": "Google account has no email"}, status=400)

    user, created = User.objects.get_or_create(
        username=email, defaults={"email": email, "is_active": True}
    )
    if created:
        user.set_unusable_password()
        user.save()
        APICustomer.objects.create(user=user, plan="free", signup_method="google")

    tokens = issue_tokens(user)
    try:
        tokens["plan"] = user.apicustomer.plan
    except APICustomer.DoesNotExist:
        tokens["plan"] = "free"

    return Response(tokens, status=200)


# ─────────── API Key Management ───────────

VALID_KEY_FEATURES = ["trip_planner", "events"]


@extend_schema(
    request={"application/json": {"type": "object", "properties": {
        "name": {"type": "string", "default": "Default Key"},
        "features": {"type": "array", "items": {"type": "string"},
                     "default": ["trip_planner", "events"],
                     "description": "Features this key can access: trip_planner, events"}
    }}},
    responses={201: {"type": "object", "properties": {
        "api_key": {"type": "string"}, "key_id": {"type": "integer"},
        "name": {"type": "string"}, "features": {"type": "array", "items": {"type": "string"}},
        "warning": {"type": "string"}
    }}},
    description="Generate new API key with selected features. Max 5 active keys. Save the key — it won't be shown again.",
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_api_key(request):
    try:
        customer = request.user.apicustomer
    except APICustomer.DoesNotExist:
        return Response({"error": "No API customer profile found"}, status=403)

    active_count = APIKey.objects.filter(customer=customer, is_active=True).count()
    if active_count >= 5:
        return Response({"error": "Maximum 5 active API keys allowed. Revoke an old one first."}, status=400)

    key_name = request.data.get("name", "Default Key")
    features = request.data.get("features")
    if features is None:
        features = list(VALID_KEY_FEATURES)
    elif isinstance(features, list):
        features = [f for f in features if f in VALID_KEY_FEATURES]
        if not features:
            return Response({"error": "Select at least one valid feature (trip_planner, events)"}, status=400)
    else:
        return Response({"error": "features must be a list of strings"}, status=400)

    raw_key, key_hash = APIKey.generate_key()

    api_key = APIKey.objects.create(
        customer=customer,
        key_hash=key_hash,
        key_prefix=raw_key[:16],
        name=key_name,
        allowed_features=features,
    )

    return Response({
        "api_key": raw_key,
        "key_id": api_key.id,
        "name": key_name,
        "features": features,
        "warning": "Save this key now. It will not be shown again.",
    }, status=201)


@extend_schema(
    responses={200: {"type": "object", "properties": {"keys": {"type": "array", "items": {
        "type": "object", "properties": {
            "id": {"type": "integer"}, "prefix": {"type": "string"}, "name": {"type": "string"},
            "is_active": {"type": "boolean"}, "created_at": {"type": "string", "format": "date-time"},
            "last_used_at": {"type": "string", "format": "date-time", "nullable": True}
        }
    }}}}},
    description="List all API keys (active and revoked).",
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_api_keys(request):
    try:
        customer = request.user.apicustomer
    except APICustomer.DoesNotExist:
        return Response({"error": "No API customer profile found"}, status=403)

    keys = APIKey.objects.filter(customer=customer).order_by('-created_at')
    data = [{
        "id": k.id, "prefix": k.key_prefix, "name": k.name,
        "is_active": k.is_active, "created_at": k.created_at,
        "last_used_at": k.last_used_at,
    } for k in keys]
    return Response({"keys": data})


@extend_schema(
    responses={200: {"type": "object", "properties": {"message": {"type": "string"}}},
               404: {"type": "object", "properties": {"error": {"type": "string"}}}},
    description="Revoke (deactivate) an API key by ID.",
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def revoke_api_key(request, key_id):
    # APICustomer.DoesNotExist yahan catch nahi ho raha tha -> 500.
    try:
        customer = request.user.apicustomer
    except APICustomer.DoesNotExist:
        return Response({"error": "No API customer profile found"}, status=403)

    try:
        key = APIKey.objects.get(id=key_id, customer=customer)
    except APIKey.DoesNotExist:
        return Response({"error": "Key not found"}, status=404)

    key.is_active = False
    key.save(update_fields=["is_active"])
    return Response({"message": "API key revoked"})
