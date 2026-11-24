from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Account, Company, CompanyMembership, Recruiter

admin.site.register(Account, UserAdmin)
admin.site.register(Company)
admin.site.register(Recruiter)
admin.site.register(CompanyMembership)
