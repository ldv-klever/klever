from django.db import migrations, models
from django.contrib.postgres.fields import ArrayField


class Migration(migrations.Migration):
    dependencies = [('marks', '0001_initial')]

    operations = [
        migrations.AlterField(model_name='safetag', name='name', field=models.CharField(max_length=1024)),
        migrations.AlterField(model_name='unsafetag', name='name', field=models.CharField(max_length=1024)),
        migrations.AlterField(model_name='marksafe', name='cache_tags', field=ArrayField(
            base_field=models.CharField(max_length=1024), default=list, size=None)
        ),
        migrations.AlterField(model_name='markunsafe', name='cache_tags', field=ArrayField(
            base_field=models.CharField(max_length=1024), default=list, size=None)
        ),
    ]
