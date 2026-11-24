from django.test import TestCase, override_settings
from django.utils import timezone

from .models import (
    Account, Company, CompanyMembership, ContactRequest,
    EncryptedSubmission, RecipientPublicKey,
    Recruit, Recruiter, SubmissionAccess,
)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
)
class PrivacyTests(TestCase):
    def setUp(self):
        recruit_account = Account.objects.create_user(
            username="candidate-account",
            email="candidate@example.test",
            password="test-password-for-tests",
        )
        self.recruit = Recruit.objects.create(account=recruit_account)

        recruiter_account = Account.objects.create_user(
            username="reviewer-account",
            email="reviewer@example.test",
            password="test-password-for-tests",
        )
        self.recruiter = Recruiter.objects.create(
            account=recruiter_account
        )
        self.company = Company.objects.create(name="Test Company")

        CompanyMembership.objects.create(
            company=self.company,
            recruiter=self.recruiter,
            status="active",
        )

        self.key = RecipientPublicKey.objects.create(
            recruiter=self.recruiter,
            public_key="test-public-key-fixture",
        )

        self.submission = EncryptedSubmission.objects.create(
            recruit=self.recruit,
            company=self.company,
            ciphertext=b"opaque-test-fixture",
        )

        self.client.force_login(recruiter_account)

    def grant(self):
        return SubmissionAccess.objects.create(
            submission=self.submission,
            recipient=self.recruiter,
            public_key=self.key,
        )

    def test_membership_does_not_grant_retrieval(self):
        response = self.client.get("/api/submissions/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])

    def test_revocation_blocks_retrieval(self):
        access = self.grant()
        self.assertEqual(
            len(self.client.get("/api/submissions/").json()["items"]), 1
        )

        access.revoked_at = timezone.now()
        access.save()

        self.assertEqual(
            self.client.get("/api/submissions/").json()["items"], []
        )

    def test_email_requires_acceptance(self):
        self.grant()
        contact = ContactRequest.objects.create(
            submission=self.submission,
            recruiter=self.recruiter,
            recruit=self.recruit,
        )

        item = self.client.get("/api/contacts/").json()["items"][0]
        self.assertNotIn("email", item)

        contact.status = "accepted"
        contact.responded_at = timezone.now()
        contact.save()

        item = self.client.get("/api/contacts/").json()["items"][0]
        self.assertEqual(item["email"], "candidate@example.test")

    def test_other_account_cannot_delete_submission(self):
        response = self.client.post(
            f"/api/submissions/{self.submission.pk}/delete/"
        )
        self.assertEqual(response.status_code, 404)

    def test_recruit_can_delete_submission(self):
        self.grant()
        self.client.force_login(self.recruit.account)

        response = self.client.post(
            f"/api/submissions/{self.submission.pk}/delete/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(EncryptedSubmission.objects.exists())
        self.assertFalse(SubmissionAccess.objects.exists())
