from django import forms
from django.contrib.auth.models import User
from django.utils.translation import ugettext_lazy as _
from users.models import Extended
from bridge.settings import DEF_USER


class UserForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput()
    )
    retype_password = forms.CharField(
        widget=forms.PasswordInput(),
        help_text=_('Confirmation'),
        required=True
    )

    def __init__(self, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)
        self.fields['password'].label = _("Password")
        self.fields['retype_password'].label = _("Confirmation")
        self.fields['email'].label = _("Email")

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
            'username': forms.TextInput(),
            'email': forms.EmailInput(),
        }


class EditUserForm(forms.ModelForm):

    new_password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={'autocomplete': 'off'}
        ),
        required=False
    )

    retype_password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={'autocomplete': 'off'}
        ),
        required=False
    )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super(EditUserForm, self).__init__(*args, **kwargs)
        self.fields['new_password'].label = _("New password")
        self.fields['retype_password'].label = _("Confirmation")

    def clean(self):
        cleaned_data = super(EditUserForm, self).clean()
        new_pass = cleaned_data.get("new_password")
        retyped = cleaned_data.get("retype_password")
        if new_pass != retyped:
            raise forms.ValidationError({
                'retype_password': _("Passwords don't match")
            })

    class Meta:
        model = User
        fields = ('new_password', 'retype_password', 'email')
        widgets = {
            'email': forms.EmailInput(),
        }


class UserExtendedForm(forms.ModelForm):
    accuracy = forms.IntegerField(widget=forms.NumberInput(), min_value=0, max_value=10, initial=DEF_USER['accuracy'])

    def __init__(self, *args, **kwargs):
        super(UserExtendedForm, self).__init__(*args, **kwargs)
        self.fields['accuracy'].label = _("The number of significant figures")
        self.fields['last_name'].label = _("Last name")
        self.fields['first_name'].label = _("First name")
        self.fields['language'].label = _("Language")
        self.fields['data_format'].label = _("Data format")
        self.fields['assumptions'].label = _("Error trace assumptions")

    class Meta:
        model = Extended
        fields = ('accuracy', 'data_format', 'language', 'first_name', 'last_name', 'assumptions')
        widgets = {
            'data_format': forms.Select(attrs={'class': 'ui selection dropdown'}),
            'language': forms.Select(attrs={'class': 'ui selection dropdown'}),
            'first_name': forms.TextInput(),
            'last_name': forms.TextInput(),
            'assumptions': forms.CheckboxInput(attrs={'class': 'hidden'})
        }
