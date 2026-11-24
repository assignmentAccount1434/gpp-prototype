import uuid

from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Account


class SignupForm(UserCreationForm):
    email = forms.EmailField()
    kind = forms.ChoiceField(
        choices=[("recruit", "Recruit"), ("recruiter", "Recruiter")]
    )

    class Meta:
        model = Account
        fields = ["email"]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if Account.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account already uses this email.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.username = "account-" + uuid.uuid4().hex
        if commit:
            user.save()
        return user
