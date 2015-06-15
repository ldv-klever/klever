from django import forms
from django.contrib.auth.models import User
from users.models import UserExtended


class UserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput())

    class Meta:
        model = User
        fields = ('username', 'email', 'password')


class UserExtendedForm(forms.ModelForm):
    class Meta:
        model = UserExtended
        fields = ('picture',)
