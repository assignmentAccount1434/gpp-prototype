import base64
import binascii
import functools
import hashlib
import json
import uuid

from bech32 import bech32_decode, convertbits
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import SignupForm
from .models import (
    Account, Company, CompanyMembership, ContactNotification,
    ContactRequest, EncryptedSubmission, RecipientPublicKey,
    Recruit, Recruiter, SubmissionAccess,
)

MAX_CIPHERTEXT = 262_144


def error(message, status=400):
    return JsonResponse({"error": message}, status=status)


def api(view):
    @functools.wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return error("Authentication required.", 401)
        try:
            return view(request, *args, **kwargs)
        except (
            ValidationError, ValueError, TypeError, KeyError,
            binascii.Error, UnicodeDecodeError,
        ):
            return error("Invalid request.")
    return wrapped


def body(request, allowed, required=None):
    if request.content_type != "application/json":
        raise ValidationError("JSON required.")
    if len(request.body) > 400_000:
        raise ValidationError("Request too large.")
    data = json.loads(request.body)
    if not isinstance(data, dict) or set(data) - set(allowed):
        raise ValidationError("Unexpected fields.")
    if set(required or allowed) - set(data):
        raise ValidationError("Missing fields.")
    return data


def limited(key, maximum, seconds=3600):
    bucket = int(timezone.now().timestamp()) // seconds
    cache_key = f"rate:{key}:{bucket}"
    if cache.add(cache_key, 1, timeout=seconds + 60):
        return False
    return cache.incr(cache_key) > maximum


def user_limited(request, operation, maximum):
    return limited(f"{operation}:{request.user.pk}", maximum)


def active_member(recruiter, company_id):
    return CompanyMembership.objects.filter(
        recruiter=recruiter,
        company_id=company_id,
        status="active",
    ).exists()


def accessible(recruiter):
    company_ids = CompanyMembership.objects.filter(
        recruiter=recruiter, status="active"
    ).values("company_id")

    return EncryptedSubmission.objects.filter(
        company_id__in=company_ids,
        accesses__recipient=recruiter,
        accesses__revoked_at__isnull=True,
    ).distinct()


def public_key(value):
    if not isinstance(value, str) or len(value) != 62:
        raise ValidationError("Native age public recipient key required.")
    hrp, words = bech32_decode(value)
    decoded = None if words is None else convertbits(words, 5, 8, False)
    if hrp != "age" or decoded is None or len(decoded) != 32:
        raise ValidationError("Invalid public recipient key.")
    return value


def fingerprint(value):
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def signup(request):
    if request.method == "POST":
        # REMOTE_ADDR must represent the client at your trusted proxy.
        if limited(f"signup:{request.META.get('REMOTE_ADDR')}", 10):
            return render(
                request, "recruitment/auth.html",
                {"form": SignupForm(), "title": "Create account",
                 "problem": "Too many attempts. Try again later."},
                status=429,
            )

    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            account = form.save()
            model = (
                Recruit if form.cleaned_data["kind"] == "recruit"
                else Recruiter
            )
            model.objects.create(account=account)
        login(request, account)
        return redirect("app")

    return render(
        request, "recruitment/auth.html",
        {"form": form, "title": "Create account"},
    )


def signin(request):
    problem = None
    if request.method == "POST":
        if limited(f"login:{request.META.get('REMOTE_ADDR')}", 30):
            problem = "Too many attempts. Try again later."
        else:
            email = request.POST.get("username", "").strip().lower()
            account = Account.objects.filter(email__iexact=email).first()
            user = authenticate(
                request,
                username=account.username if account else "__missing__",
                password=request.POST.get("password", ""),
            )
            if user:
                login(request, user)
                return redirect("app")
            problem = "Invalid email or password."

    form = AuthenticationForm(request)
    form.fields["username"].label = "Account email"
    return render(
        request, "recruitment/auth.html",
        {"form": form, "title": "Sign in", "problem": problem},
    )


@login_required
def app(request):
    return render(request, "recruitment/app.html")


@require_GET
@api
def bootstrap(request):
    recruit = Recruit.objects.filter(account=request.user).first()
    recruiter = Recruiter.objects.filter(account=request.user).first()
    if not recruit and not recruiter:
        return error("No recruitment role assigned.", 403)

    companies = []
    for company in Company.objects.order_by("name", "pk"):
        keys = RecipientPublicKey.objects.filter(
            active=True,
            recruiter__companymembership__company=company,
            recruiter__companymembership__status="active",
        ).distinct().order_by("pk")

        companies.append({
            "id": company.pk,
            "name": company.name,
            "recipients": [{
                "key_id": key.pk,
                "recipient_id": key.recruiter_id,
                "public_key": key.public_key,
                "version": str(key.version),
                "fingerprint": fingerprint(key.public_key),
            } for key in keys],
        })

    own_keys = RecipientPublicKey.objects.filter(
        recruiter=recruiter
    ).order_by("-created_at") if recruiter else []

    return JsonResponse({
        "kind": "recruit" if recruit else "recruiter",
        "companies": companies,
        "keys": [{
            "id": key.pk,
            "public_key": key.public_key,
            "version": str(key.version),
            "active": key.active,
        } for key in own_keys],
    })


@require_POST
@api
def publish_key(request):
    recruiter = get_object_or_404(Recruiter, account=request.user)
    if user_limited(request, "key", 20):
        return error("Rate limit reached.", 429)
    data = body(request, ["public_key"])
    key = public_key(data["public_key"])
    record, _ = RecipientPublicKey.objects.get_or_create(
        recruiter=recruiter, public_key=key
    )
    return JsonResponse({
        "id": record.pk, "version": str(record.version),
        "active": record.active,
    })


@require_POST
@api
def retire_key(request, key_id):
    with transaction.atomic():
        key = get_object_or_404(
            RecipientPublicKey.objects.select_for_update(),
            pk=key_id, recruiter__account=request.user,
        )
        key.active = False
        key.retired_at = key.retired_at or timezone.now()
        key.save(update_fields=["active", "retired_at"])
    return JsonResponse({"status": "retired"})


@require_POST
@api
def submit(request):
    recruit = get_object_or_404(Recruit, account=request.user)
    if user_limited(request, "submit", 20):
        return error("Rate limit reached.", 429)

    data = body(request, [
        "company_id", "key_ids", "ciphertext",
        "encryption_format", "payload_schema_version",
    ])

    ids = data["key_ids"]
    if (
        data["encryption_format"] != "age-v1"
        or type(data["payload_schema_version"]) is not int
        or data["payload_schema_version"] != 1
        or type(data["company_id"]) is not int
        or not isinstance(ids, list)
        or not 1 <= len(ids) <= 10
        or any(type(x) is not int for x in ids)
        or len(set(ids)) != len(ids)
        or not isinstance(data["ciphertext"], str)
    ):
        raise ValidationError("Invalid envelope.")

    ciphertext = base64.b64decode(data["ciphertext"], validate=True)
    if (
        not 1 <= len(ciphertext) <= MAX_CIPHERTEXT
        or not ciphertext.startswith(b"age-encryption.org/v1\n")
    ):
        raise ValidationError("Invalid age ciphertext envelope.")

    company = get_object_or_404(Company, pk=data["company_id"])

    with transaction.atomic():
        keys = list(
            RecipientPublicKey.objects.select_for_update().filter(
                pk__in=ids, active=True
            )
        )

        memberships = list(
            CompanyMembership.objects.select_for_update().filter(
                company=company,
                recruiter_id__in=[key.recruiter_id for key in keys],
                status="active",
            )
        )
        members = {m.recruiter_id for m in memberships}

        if len(keys) != len(ids) or any(
            key.recruiter_id not in members for key in keys
        ):
            return error("Recipients changed. Verify and encrypt again.", 409)

        submission = EncryptedSubmission.objects.create(
            recruit=recruit, company=company, ciphertext=ciphertext
        )
        SubmissionAccess.objects.bulk_create([
            SubmissionAccess(
                submission=submission,
                recipient=key.recruiter,
                public_key=key,
            ) for key in keys
        ])

    return JsonResponse({"id": str(submission.pk)}, status=201)


@require_GET
@api
def submissions(request):
    recruit = Recruit.objects.filter(account=request.user).first()
    if recruit:
        rows = EncryptedSubmission.objects.filter(
            recruit=recruit
        ).select_related("company").prefetch_related(
            "accesses"
        ).order_by("-created_at", "pk")

        return JsonResponse({"items": [{
            "id": str(row.pk),
            "company": row.company.name,
            "created_at": row.created_at.isoformat(),
            "status": row.status,
            "accesses": [{
                "id": access.pk,
                "recipient_id": access.recipient_id,
                "revoked": access.revoked_at is not None,
            } for access in row.accesses.all()],
        } for row in rows]})

    recruiter = get_object_or_404(Recruiter, account=request.user)
    rows = accessible(recruiter)
    total = rows.count()

    after = request.GET.get("after")
    if after:
        after = uuid.UUID(after)
        rows = rows.filter(pk__gt=after)

    # UUID ordering is stable and is not suitability ranking.
    page = list(rows.order_by("pk")[:51])
    has_more = len(page) > 50
    page = page[:50]

    return JsonResponse({
        "total": total,
        "next": str(page[-1].pk) if has_more else None,
        "items": [{
            "id": str(row.pk),
            "created_at": row.created_at.isoformat(),
            "ciphertext": base64.b64encode(
                bytes(row.ciphertext)
            ).decode("ascii"),
        } for row in page],
    })


@require_POST
@api
def delete_submission(request, submission_id):
    row = get_object_or_404(
        EncryptedSubmission,
        pk=submission_id,
        recruit__account=request.user,
    )
    row.delete()
    return JsonResponse({"status": "deleted"})


@require_POST
@api
def revoke_access(request, access_id):
    access = get_object_or_404(
        SubmissionAccess,
        pk=access_id,
        submission__recruit__account=request.user,
    )
    access.revoked_at = access.revoked_at or timezone.now()
    access.save(update_fields=["revoked_at"])
    return JsonResponse({"status": "revoked"})


@require_POST
@api
def request_contact(request, submission_id):
    recruiter = get_object_or_404(Recruiter, account=request.user)
    submission = get_object_or_404(
        accessible(recruiter), pk=submission_id
    )
    if user_limited(request, "contact", 30):
        return error("Rate limit reached.", 429)

    with transaction.atomic():
        contact, created = ContactRequest.objects.get_or_create(
            submission=submission,
            recruiter=recruiter,
            defaults={"recruit": submission.recruit},
        )
        if created:
            ContactNotification.objects.create(contact_request=contact)

    return JsonResponse({"id": contact.pk, "status": contact.status})


@require_GET
@api
def contacts(request):
    recruit = Recruit.objects.filter(account=request.user).first()
    if recruit:
        rows = ContactRequest.objects.filter(
            recruit=recruit
        ).select_related("submission__company").order_by("-created_at")

        return JsonResponse({"items": [{
            "id": row.pk,
            "submission_id": str(row.submission_id),
            "company": row.submission.company.name,
            "requester_id": row.recruiter_id,
            "status": row.status,
        } for row in rows]})

    recruiter = get_object_or_404(Recruiter, account=request.user)
    rows = ContactRequest.objects.filter(
        recruiter=recruiter,
        submission__in=accessible(recruiter),
    ).select_related("recruit__account").order_by("-created_at")

    return JsonResponse({"items": [{
        "id": row.pk,
        "submission_id": str(row.submission_id),
        "status": row.status,
        **(
            {"email": row.recruit.account.email}
            if row.status == "accepted" else {}
        ),
    } for row in rows]})


@require_POST
@api
def respond_contact(request, contact_id):
    data = body(request, ["status"])
    if data["status"] not in ["accepted", "declined"]:
        raise ValidationError("Invalid response.")

    with transaction.atomic():
        contact = get_object_or_404(
            ContactRequest.objects.select_for_update(),
            pk=contact_id,
            recruit__account=request.user,
        )
        if contact.status != "pending":
            return error("This request was already answered.", 409)

        contact.status = data["status"]
        contact.responded_at = timezone.now()
        contact.save(update_fields=["status", "responded_at"])

    return JsonResponse({"status": contact.status})
