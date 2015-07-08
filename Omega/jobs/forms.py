from django import forms
from jobs.models import Job, File


class JobForm(forms.ModelForm):
    # format_version = forms.IntegerField(widget=forms.HiddenInput())
    job_id = forms.CharField(widget=forms.HiddenInput())
    version = forms.IntegerField(widget=forms.HiddenInput(), initial=1)
    lastchange_author = forms.CharField(widget=forms.HiddenInput())
    lastchange_date = forms.DateField(widget=forms.HiddenInput())
    parent = forms.CharField(widget=forms.HiddenInput(), required=False)
    user_roles = forms.CharField(widget=forms.HiddenInput())
    global_roles = forms.CharField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = Job
        fields = [
            'name',
            'type',
            'comment',
            'configuration',
        ]

class FileForm(forms.ModelForm):
    ver_job = forms.ModelChoiceField(queryset=Job.objects.all(),
                                     widget=forms.HiddenInput())

    class Meta:
        model = File
        fields = ['ver_job']
