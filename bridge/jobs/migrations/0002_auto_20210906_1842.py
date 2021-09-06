from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('jobs', '0001_initial')]

    operations = [
        migrations.AlterField(
            model_name='presetjob', name='name',
            field=models.CharField(db_index=True, max_length=150, verbose_name='Name'),
        ),
        migrations.AlterUniqueTogether(name='presetjob', unique_together={('parent', 'name')}),
    ]
