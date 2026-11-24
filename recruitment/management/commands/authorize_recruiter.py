from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from recruitment.models import Company, CompanyMembership, Recruiter


class Command(BaseCommand):
    help = "Explicitly authorize an existing recruiter for a company."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--company-id", type=int)
        parser.add_argument("--new-company")

    @transaction.atomic
    def handle(self, *args, **options):
        if bool(options["company_id"]) == bool(options["new_company"]):
            raise CommandError(
                "Supply exactly one of --company-id or --new-company."
            )

        try:
            recruiter = Recruiter.objects.get(
                account__email__iexact=options["email"].strip()
            )
        except Recruiter.DoesNotExist:
            raise CommandError("Recruiter account not found.")

        if options["company_id"]:
            try:
                company = Company.objects.get(pk=options["company_id"])
            except Company.DoesNotExist:
                raise CommandError("Company not found.")
        else:
            company = Company.objects.create(name=options["new_company"])

        CompanyMembership.objects.update_or_create(
            company=company,
            recruiter=recruiter,
            defaults={"status": "active", "role": "recruiter"},
        )

        self.stdout.write(
            f"Authorized recipient {recruiter.pk} for company {company.pk}. "
            "No historical submission access was granted."
        )
