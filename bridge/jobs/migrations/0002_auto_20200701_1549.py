from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('jobs', '0001_initial')]

    operations = [
        migrations.AddField(
            model_name='uploadedjobarchive', name='step_progress',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='uploadedjobarchive', name='status',
            field=models.CharField(choices=[
                ('0', 'Pending'), ('1', 'Extracting archive files'), ('2', 'Uploading files'), ('3', 'Uploading job'),
                ('4', 'Uploading decisions cache'), ('5', 'Uploading original sources'),
                ('6', 'Uploading reports trees'), ('7', 'Uploading safes'), ('8', 'Uploading unsafes'),
                ('9', 'Uploading unknowns'), ('10', 'Uploading attributes'), ('11', 'Uploading coverage'),
                ('12', 'Associating marks and cache recalculation'), ('13', 'Finished'), ('14', 'Failed')
            ], default='0', max_length=2),
        ),
    ]
