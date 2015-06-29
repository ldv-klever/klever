from django import forms
from django.contrib.auth.models import User
from users.models import UserExtended


class UserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput())
    retype_password = forms.CharField(widget=forms.PasswordInput(),
                                      help_text='Retype password',
                                      required=True)

    def clean(self):
        cleaned_data = super(UserForm, self).clean()
        password = cleaned_data.get("password")
        retyped = cleaned_data.get("retype_password")
        if password != retyped:
            raise forms.ValidationError("Passwords don't match")

    class Meta:
        model = User
        fields = ('username', 'password', 'retype_password', 'email')


class EditUserForm(forms.ModelForm):

    old_password = forms.CharField(widget=forms.PasswordInput(),
                                   required=False, help_text='Old password',
                                   initial=None)

    new_password = forms.CharField(widget=forms.PasswordInput(),
                                   help_text='New password',
                                   required=False)
    retype_password = forms.CharField(widget=forms.PasswordInput(),
                                      help_text='Retype password',
                                      required=False)

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super(EditUserForm, self).__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super(EditUserForm, self).clean()
        old_pass = cleaned_data.get("old_password")
        new_pass = cleaned_data.get("new_password")
        retyped = cleaned_data.get("retype_password")
        if new_pass != retyped:
            raise forms.ValidationError("Passwords don't match")
        if self.request:
            if not self.request.user.check_password(old_pass):
                raise forms.ValidationError("Wrong old password")

    class Meta:
        model = User
        fields = ('old_password', 'new_password', 'retype_password', 'email')


class UserExtendedForm(forms.ModelForm):
    accuracy = forms.IntegerField(min_value=0, max_value=10,
                                  help_text='Prefered accuracy',
                                  initial=2)

    class Meta:
        model = UserExtended
        # TODO: remove 'role' after testing
        fields = ('accuracy', 'language', 'role', 'first_name', 'last_name')
