import random
import secrets
import hashlib
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from datetime import timedelta


class APICustomer(models.Model):
    PLAN_CHOICES = [
        ("free", "Free"), ("starter", "Starter"),
        ("pro", "Pro"), ("business", "Business"),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    company_name = models.CharField(max_length=150, blank=True)
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default="free")
    is_active = models.BooleanField(default=True)
    signup_method = models.CharField(max_length=20, default="email")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ({self.plan})"


class APICallLog(models.Model):
    customer = models.ForeignKey(APICustomer, on_delete=models.CASCADE)
    endpoint = models.CharField(max_length=200)
    timestamp = models.DateTimeField(auto_now_add=True)


class OTPVerification(models.Model):
    PURPOSE_CHOICES = [
        ("register", "Registration"),
        ("password_reset", "Password Reset"),
    ]
    email = models.EmailField()
    otp_code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    is_used = models.BooleanField(default=False)
    attempts = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    @staticmethod
    def generate_otp():
        return str(random.randint(100000, 999999))

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at and self.attempts < 5

    class Meta:
        ordering = ['-created_at']


# ──────────────────────────────────────────────────────────────
# FreeUsage — IP-based daily limit for anonymous users.
# Yeh IP-based limit sirf WEBSITE (Trip Planner, Event Risk) ke
# liye hai. B2B API (/api/v1/...) ka apna alag PLAN_LIMITS
# system hai (api_subscription app mein) — yeh dono independent
# hain, conflict nahi karte.
# ──────────────────────────────────────────────────────────────
class FreeUsage(models.Model):
    ip_address = models.GenericIPAddressField()
    endpoint = models.CharField(max_length=50)
    date = models.DateField(auto_now_add=True)
    count = models.IntegerField(default=1)

    class Meta:
        unique_together = ('ip_address', 'endpoint', 'date')

    def __str__(self):
        return f"{self.ip_address} | {self.endpoint} | {self.date} | {self.count}"


class APIKey(models.Model):
    customer = models.ForeignKey(APICustomer, on_delete=models.CASCADE, related_name='api_keys')
    key_hash = models.CharField(max_length=64, unique=True)
    key_prefix = models.CharField(max_length=16)
    name = models.CharField(max_length=100, blank=True)
    allowed_features = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    @staticmethod
    def generate_key():
        raw_key = f"wv_live_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        return raw_key, key_hash

    def __str__(self):
        return f"{self.key_prefix}... ({self.customer.user.username})"


class APIRequestLog(models.Model):
    api_key = models.ForeignKey(APIKey, on_delete=models.CASCADE, related_name='logs')
    endpoint = models.CharField(max_length=100)
    status_code = models.IntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['api_key', 'timestamp']),
        ]
