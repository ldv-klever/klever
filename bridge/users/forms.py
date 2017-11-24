#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from django import forms
from django.conf import settings
from django.contrib.auth.models import User
from django.utils.translation import ugettext_lazy as _
from users.models import Extended


class UserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput())
    retype_password = forms.CharField(widget=forms.PasswordInput(), help_text=_('Confirmation'), required=True)
    first_name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)

    def __init__(self, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)
        self.fields['password'].label = _("Password")
        self.fields['retype_password'].label = _("Confirmation")
        self.fields['email'].label = _("Email")
        self.fields['first_name'].label = _("First name")
        self.fields['last_name'].label = _("Last name")

    def clean_retype_password(self):
        cleaned_data = super(UserForm, self).clean()
        password = cleaned_data.get("password")
        retyped = cleaned_data.get("retype_password")
        if password != retyped:
            raise forms.ValidationError("Passwords don't match")

    class Meta:
        model = User
        fields = ('username', 'password', 'retype_password', 'email', 'first_name', 'last_name')
        widgets = {
            'username': forms.TextInput(),
            'email': forms.EmailInput(),
            'first_name': forms.TextInput(),
            'last_name': forms.TextInput()
        }


class EditUserForm(forms.ModelForm):
    new_password = forms.CharField(widget=forms.PasswordInput(attrs={'autocomplete': 'off'}), required=False)
    retype_password = forms.CharField(widget=forms.PasswordInput(attrs={'autocomplete': 'off'}), required=False)
    first_name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super(EditUserForm, self).__init__(*args, **kwargs)
        self.fields['new_password'].label = _("New password")
        self.fields['retype_password'].label = _("Confirmation")
        self.fields['first_name'].label = _("First name")
        self.fields['last_name'].label = _("Last name")

    def clean_retype_password(self):
        cleaned_data = super(EditUserForm, self).clean()
        new_pass = cleaned_data.get("new_password")
        retyped = cleaned_data.get("retype_password")
        if new_pass != retyped:
            raise forms.ValidationError(_("Passwords don't match"))

    class Meta:
        model = User
        fields = ('new_password', 'retype_password', 'email', 'first_name', 'last_name')
        widgets = {
            'email': forms.EmailInput(),
            'first_name': forms.TextInput(),
            'last_name': forms.TextInput()
        }


class UserExtendedForm(forms.ModelForm):
    accuracy = forms.IntegerField(widget=forms.NumberInput(), min_value=0, max_value=10,
                                  initial=settings.DEF_USER['accuracy'])

    def __init__(self, *args, **kwargs):
        super(UserExtendedForm, self).__init__(*args, **kwargs)
        self.fields['accuracy'].label = _("The number of significant figures")
        self.fields['language'].label = _("Language")
        self.fields['data_format'].label = _("Data format")
        self.fields['assumptions'].label = _("Error trace assumptions")
        self.fields['triangles'].label = _("Error trace closing triangles")
        self.fields['coverage_data'].label = _("Coverage data")

    class Meta:
        model = Extended
        fields = ('accuracy', 'data_format', 'language', 'assumptions', 'triangles', 'coverage_data')
        widgets = {
            'data_format': forms.Select(attrs={'class': 'ui selection dropdown'}),
            'language': forms.Select(attrs={'class': 'ui selection dropdown'}),
            'assumptions': forms.CheckboxInput(attrs={'class': 'hidden'}),
            'triangles': forms.CheckboxInput(attrs={'class': 'hidden'}),
            'coverage_data': forms.CheckboxInput(attrs={'class': 'hidden'})
        }
