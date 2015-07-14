from django import forms
from jobs.models import Job, File


class FileForm(forms.ModelForm):
    ver_job = forms.ModelChoiceField(queryset=Job.objects.all(),
                                     widget=forms.HiddenInput())

    class Meta:
        model = File
        fields = ['ver_job']
