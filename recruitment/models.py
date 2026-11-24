import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower


class Account(AbstractUser):
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("email"), name="account_email_case_insensitive"
            )
        ]


class Recruit(models.Model):
    account = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE
    )
    candidate_identifier = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False
    )


class Recruiter(models.Model):
    account = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE
    )


class Company(models.Model):
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)


class CompanyMembership(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    recruiter = models.ForeignKey(Recruiter, on_delete=models.CASCADE)
    role = models.CharField(
        max_length=20,
        choices=[("admin", "Administrator"), ("recruiter", "Recruiter")],
        default="recruiter",
    )
    status = models.CharField(
        max_length=20,
        choices=[("active", "Active"), ("inactive", "Inactive")],
        default="inactive",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "recruiter"],
                name="unique_company_membership",
            )
        ]


class RecipientPublicKey(models.Model):
    recruiter = models.ForeignKey(Recruiter, on_delete=models.PROTECT)
    public_key = models.CharField(max_length=62)
    version = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["recruiter", "public_key"],
                name="unique_recruiter_public_key",
            )
        ]


class EncryptedSubmission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recruit = models.ForeignKey(Recruit, on_delete=models.CASCADE)
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    ciphertext = models.BinaryField()
    encryption_format = models.CharField(max_length=20, default="age-v1")
    payload_schema_version = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=20, default="submitted")
    created_at = models.DateTimeField(auto_now_add=True)


class SubmissionAccess(models.Model):
    submission = models.ForeignKey(
        EncryptedSubmission,
        on_delete=models.CASCADE,
        related_name="accesses",
    )
    recipient = models.ForeignKey(Recruiter, on_delete=models.PROTECT)
    public_key = models.ForeignKey(RecipientPublicKey, on_delete=models.PROTECT)
    granted_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["submission", "public_key"],
                name="unique_submission_public_key",
            )
        ]


class ContactRequest(models.Model):
    submission = models.ForeignKey(
        EncryptedSubmission, on_delete=models.CASCADE
    )
    recruiter = models.ForeignKey(Recruiter, on_delete=models.PROTECT)
    recruit = models.ForeignKey(Recruit, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=10,
        choices=[
            ("pending", "Pending"),
            ("accepted", "Accepted"),
            ("declined", "Declined"),
        ],
        default="pending",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["submission", "recruiter"],
                name="unique_contact_request",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status="pending", responded_at__isnull=True)
                    | Q(
                        status__in=["accepted", "declined"],
                        responded_at__isnull=False,
                    )
                ),
                name="consistent_contact_response",
            ),
        ]


class ContactNotification(models.Model):
    contact_request = models.OneToOneField(
        ContactRequest, on_delete=models.CASCADE
    )
    status = models.CharField(
        max_length=12,
        choices=[
            ("queued", "Queued"),
            ("sending", "Sending"),
            ("sent", "Sent"),
            ("unknown", "Unknown"),
        ],
        default="queued",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
