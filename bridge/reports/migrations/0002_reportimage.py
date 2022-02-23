import bridge.utils
from django.db import migrations, models
import reports.models


class Migration(migrations.Migration):
    dependencies = [('reports', '0001_initial')]

    operations = [
        migrations.CreateModel(name='ReportImage', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('title', models.TextField()),
            ('image', models.FileField(upload_to=reports.models.get_images_path)),
            ('data', models.FileField(upload_to=reports.models.get_images_path)),
            ('report', models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name='images', to='reports.ReportComponent'
            )),
        ], options={'db_table': 'report_component_images'}, bases=(bridge.utils.WithFilesMixin, models.Model)),
    ]
