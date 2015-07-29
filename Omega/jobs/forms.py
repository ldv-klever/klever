from django import forms
from jobs.models import Job, File


class FileForm(forms.ModelForm):
    file = forms.FileField()

    class Meta:
        model = File
        fields = ['file']
