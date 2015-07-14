from django import forms
from django.contrib.auth.models import User
from users.models import Extended
from django.utils.translation import ugettext_lazy as _


class UserForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    retype_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        help_text='Retype password',
        required=True
    )

    def __init__(self, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)
        self.fields['password'].label = _("Password")

    def clean(self):
        cleaned_data = super(UserForm, self).clean()
        password = cleaned_data.get("password")
        retyped = cleaned_data.get("retype_password")
        if password != retyped:
            raise forms.ValidationError("Passwords don't match")

    class Meta:
        model = User
        fields = ('username', 'password', 'retype_password', 'email')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }


class EditUserForm(forms.ModelForm):

    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        required=False
    )

    retype_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        required=False
    )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super(EditUserForm, self).__init__(*args, **kwargs)
        self.fields['new_password'].label = _("New password")
        self.fields['retype_password'].label = _("Retype password")

    def clean(self):
        cleaned_data = super(EditUserForm, self).clean()
        new_pass = cleaned_data.get("new_password")
        retyped = cleaned_data.get("retype_password")
        if new_pass != retyped:
            raise forms.ValidationError("Passwords don't match")

    class Meta:
        model = User
        fields = ('new_password', 'retype_password', 'email')
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }


class UserExtendedForm(forms.ModelForm):
    accuracy = forms.IntegerField(
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        min_value=0, max_value=10, initial=2
    )

    def __init__(self, *args, **kwargs):
        super(UserExtendedForm, self).__init__(*args, **kwargs)
        self.fields['accuracy'].label = _("Accuracy")
        self.fields['last_name'].label = _("Last name")
        self.fields['first_name'].label = _("First name")
        self.fields['language'].label = _("Language")
        self.fields['data_format'].label = _("Data format")

    class Meta:
        model = Extended
        # TODO: remove 'role' after testing
        fields = ('accuracy', 'data_format', 'language', 'role', 'first_name', 'last_name')
        widgets = {
            'data_format': forms.Select(attrs={'class': 'form-control'}),
            'language': forms.Select(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-control'}),
        }
