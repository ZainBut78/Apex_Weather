from django.core.mail import send_mail
from django.utils import timezone
from datetime import timedelta
from .models import OTPVerification


def create_and_send_otp(email, purpose):
    OTPVerification.objects.filter(email=email, purpose=purpose, is_used=False).update(is_used=True)

    otp_code = OTPVerification.generate_otp()
    OTPVerification.objects.create(
        email=email,
        otp_code=otp_code,
        purpose=purpose,
        expires_at=timezone.now() + timedelta(minutes=10),
    )

    subject = "WeatherApex — Your Verification Code" if purpose == "register" else "WeatherApex — Password Reset Code"
    message = f"Your OTP code is: {otp_code}\nThis code expires in 10 minutes."

    send_mail(subject, message, "noreply@weatherapex.com", [email], fail_silently=False)
    return otp_code


def verify_otp(email, otp_code, purpose):
    otp_obj = OTPVerification.objects.filter(
        email=email, purpose=purpose, is_used=False
    ).order_by('-created_at').first()

    if not otp_obj:
        return False, "No OTP found. Request a new one."
    if not otp_obj.is_valid():
        return False, "OTP expired or too many attempts. Request a new one."

    otp_obj.attempts += 1
    otp_obj.save()

    if otp_obj.otp_code != otp_code:
        return False, "Invalid OTP"

    otp_obj.is_used = True
    otp_obj.save()
    return True, "OTP verified"
