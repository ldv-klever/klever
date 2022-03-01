#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
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

import pytz

from django import forms
from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm, UsernameField, UserCreationForm
from django.forms.widgets import Input
from django.utils.translation import ugettext_lazy as _

from users.models import User, SchedulerUser


class SematicUISelect(forms.Select):
    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        widget_class = {'ui', 'dropdown'}
        if 'class' in context['widget']['attrs']:
            widget_class |= set(context['widget']['attrs']['class'].split())
        context['widget']['attrs']['class'] = ' '.join(widget_class)
        return context


class SemanticUICheckbox(forms.CheckboxInput):

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        widget_class = {'hidden'}
        if 'class' in context['widget']['attrs']:
            widget_class |= set(context['widget']['attrs']['class'].split())
        context['widget']['attrs']['class'] = ' '.join(widget_class)
        return context


class SemanticPercentInput(Input):
    input_type = 'range'
    template_name = 'bridge/forms/percent.html'
    default_color = 'orange'

    def __init__(self, *args, **kwargs):
        self.step = kwargs.pop('step', 5)

        self.identifier = kwargs.pop('identifier', 'default_range_identifier')
        self.preview_id = kwargs.pop('preview_id', None)
        self.color = kwargs.pop('color', self.default_color)
        super(SemanticPercentInput, self).__init__(*args, **kwargs)

    def format_value(self, value):
        if isinstance(value, str):
            try:
                return str(int(value))
            except TypeError or ValueError:
                value = None
        return str(round(value * 100)) if value else '0'

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['widget'].update({
            'step': self.step,
            'identifier': self.identifier,
            'preview_id': self.preview_id,
            'color': self.color
        })
        return context


class SchedulerUsernameField(UsernameField):
    def widget_attrs(self, widget):
        attrs = super().widget_attrs(widget)
        attrs['autocomplete'] = 'off'
        return attrs


class FormColumnsMixin:
    form_columns = ()

    def column_iterator(self, column_id):
        for name in self.form_columns[column_id]:
            yield self[name]

    def __getitem__(self, item):
        if item.startswith('column_'):
            column_id = int(item.replace('column_', ''))
            if len(self.form_columns) > column_id:
                return self.column_iterator(column_id)
        return getattr(super(), '__getitem__')(item)


class BridgeAuthForm(AuthenticationForm):
    error_messages = {
        'invalid_login': _(
            "Please enter a correct %(username)s and password. Note that both fields may be case-sensitive."
        ),
        'inactive': _("This account is inactive. Please contact administrator to activate it."),
    }

    username = UsernameField(widget=forms.TextInput(attrs={'placeholder': _('Username'), 'autofocus': True}))
    password = forms.CharField(
        label=_("Password"), strip=False,
        widget=forms.PasswordInput(attrs={'placeholder': _('Password')}),
    )


class RegisterForm(FormColumnsMixin, UserCreationForm):
    form_columns = (
        ('username', 'password1', 'password2'),
        ('email', 'first_name', 'last_name'),
        ('accuracy', 'data_format', 'language', 'timezone')
    )

    timezone = forms.ChoiceField(
        label=_('Time zone'), widget=SematicUISelect(attrs={'class': 'search'}),
        choices=list((x, x) for x in pytz.common_timezones), initial=settings.DEF_USER['timezone']
    )
    accuracy = forms.IntegerField(
        widget=forms.NumberInput(), min_value=0, max_value=10, initial=settings.DEF_USER['accuracy']
    )
    first_name = forms.CharField(label=_('First name'), max_length=30, required=True)
    last_name = forms.CharField(label=_('Last name'), max_length=150, required=True)

    def save(self, commit=True):
        user = super(RegisterForm, self).save(commit=False)
        user.is_active = False
        if commit:
            user.save()
        return user

    class Meta:
        model = User
        field_classes = {'username': UsernameField}
        fields = ('username', 'email', 'first_name', 'last_name', 'data_format', 'language')
        widgets = {'data_format': SematicUISelect(), 'language': SematicUISelect()}


class EditProfileForm(FormColumnsMixin, forms.ModelForm):
    form_columns = (
        ('new_password1', 'new_password2', 'email', 'first_name', 'last_name'),
        (
            'accuracy', 'data_format', 'language', 'timezone', 'assumptions', 'triangles',
            'coverage_data', 'default_threshold', 'declarations_number', 'notes_level'
        )
    )
    error_messages = {
        'password_mismatch': _("Passwords don't match."),
        'sch_login_required': _('Specify username')
    }

    new_password1 = forms.CharField(
        label=_("New password"), required=False,
        widget=forms.PasswordInput(attrs={'autocomplete': "new-password"})
    )
    new_password2 = forms.CharField(
        label=_("New password confirmation"), required=False,
        widget=forms.PasswordInput(attrs={'autocomplete': "new-password"})
    )
    timezone = forms.ChoiceField(
        label=_('Time zone'), widget=SematicUISelect(attrs={'class': 'search'}),
        choices=list((x, x) for x in pytz.common_timezones), initial=settings.DEF_USER['timezone']
    )
    default_threshold = forms.IntegerField(
        label=_('Default unsafe marks threshold'),
        help_text=_('This setting sets default unsafe marks threshold on its creation'),
        min_value=0, max_value=100, widget=SemanticPercentInput(
            identifier='default_threshold_id', preview_id='default_threshold_preview'
        )
    )

    def clean_new_password2(self):
        password1 = self.cleaned_data.get('new_password1')
        password2 = self.cleaned_data.get('new_password2')
        if password1 != password2:
            raise forms.ValidationError(
                self.error_messages['password_mismatch'],
                code='password_mismatch',
            )
        elif password2:
            # Validate if passwords similar and both specified
            password_validation.validate_password(password2, self.instance)
        return password2

    def clean_default_threshold(self):
        return self.cleaned_data.get('default_threshold') / 100

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data["new_password1"]
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user

    class Meta:
        model = User
        fields = (
            'email', 'first_name', 'last_name', 'data_format', 'language',
            'accuracy', 'assumptions', 'triangles', 'coverage_data',
            'default_threshold', 'declarations_number', 'notes_level'
        )
        widgets = {
            'data_format': SematicUISelect(),
            'language': SematicUISelect(),
            'assumptions': SemanticUICheckbox(),
            'triangles': SemanticUICheckbox(),
            'coverage_data': SemanticUICheckbox(),
        }


class SchedulerUserForm(forms.ModelForm):
    error_messages = {
        'login_required': _('Specify username'),
        'password_required': _('Specify password'),
        'password_mismatch': _("Passwords don't match."),
    }
    login = SchedulerUsernameField(label=_('Username'), max_length=128, required=False)
    password1 = forms.CharField(label=_("Password"), widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(label=_("Confirmation"), required=False, widget=forms.PasswordInput)

    def clean_password1(self):
        password1 = self.cleaned_data.get('password1')
        if not getattr(self.instance, 'pk', None) and self.cleaned_data.get('login') and not password1:
            raise forms.ValidationError(self.error_messages['password_required'], code='password_required')
        return password1

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1') or ''
        password2 = self.cleaned_data.get('password2') or ''
        if password1 != password2:
            raise forms.ValidationError(self.error_messages['password_mismatch'], code='password_mismatch')
        elif password2:
            # Validate if passwords similar and both specified
            password_validation.validate_password(password2, self.instance)
        return password2

    def clean(self):
        if not self.cleaned_data.get('login') and self.cleaned_data.get('password2'):
            self.add_error('login', self.error_messages['login_required'])
        return super().clean()

    def save(self, commit=True):
        if self.cleaned_data['login']:
            self.instance.password = self.cleaned_data['password2']
            return super(SchedulerUserForm, self).save(commit)
        elif getattr(self.instance, 'pk', None):
            self.instance.delete()
        return None

    class Meta:
        model = SchedulerUser
        fields = ('login', 'password1', 'password2')
