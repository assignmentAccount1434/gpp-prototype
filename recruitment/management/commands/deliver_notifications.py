import time

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db import transaction

from recruitment.models import ContactNotification


class Command(BaseCommand):
    help = "Deliver queued generic contact notifications."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true")

    def handle(self, *args, **options):
        while True:
            self.deliver_one()
            if not options["loop"]:
                return
            time.sleep(2)

    def deliver_one(self):
        with transaction.atomic():
            notification = (
                ContactNotification.objects.select_for_update(
                    skip_locked=True
                )
                .filter(status="queued")
                .select_related("contact_request__recruit__account")
                .order_by("pk")
                .first()
            )
            if not notification:
                return

            notification.status = "sending"
            notification.save(update_fields=["status", "updated_at"])
            notification_id = notification.pk
            destination = notification.contact_request.recruit.account.email

        try:
            count = send_mail(
                "Recruitment contact request",
                "You have a recruitment contact request. Sign in to accept "
                "or decline. Accepting shares your account email with the "
                "requesting recruiter.\n\n"
                + settings.PUBLIC_BASE_URL + "/",
                settings.DEFAULT_FROM_EMAIL,
                [destination],
            )
            status = "sent" if count == 1 else "unknown"
        except Exception:
            # No automatic resend: delivery may have occurred before failure.
            status = "unknown"

        ContactNotification.objects.filter(
            pk=notification_id
        ).update(status=status)
