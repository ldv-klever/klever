from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('caches', '0002_alter_reportsafecache_attrs_and_more'),
    ]

    operations = [
        migrations.AlterField(model_name='reportsafecache', name='verdict', field=models.CharField(
            choices=[
                ('0', 'Uncertainty'), ('1', 'Incorrect proof'), ('2', 'Missed target bug'),
                ('3', 'Incompatible marks'), ('4', 'Without marks')
            ], default='4', max_length=1
        )),

        migrations.AlterField(model_name='reportunsafecache', name='verdict', field=models.CharField(
            choices=[
                ('0', 'Uncertainty'), ('1', 'Bug'), ('2', 'Target bug'), ('3', 'False positive'),
                ('4', 'Incompatible marks'), ('5', 'Without marks')
            ], default='5', max_length=1
        )),

        migrations.AlterField(model_name='safemarkassociationchanges', name='verdict_new', field=models.CharField(
            choices=[
                ('0', 'Uncertainty'), ('1', 'Incorrect proof'), ('2', 'Missed target bug'),
                ('3', 'Incompatible marks'), ('4', 'Without marks')
            ], max_length=1
        )),

        migrations.AlterField(model_name='safemarkassociationchanges', name='verdict_old', field=models.CharField(
            choices=[
                ('0', 'Uncertainty'), ('1', 'Incorrect proof'), ('2', 'Missed target bug'),
                ('3', 'Incompatible marks'), ('4', 'Without marks')
            ], max_length=1
        )),

        migrations.AlterField(model_name='unsafemarkassociationchanges', name='verdict_new', field=models.CharField(
            choices=[
                ('0', 'Uncertainty'), ('1', 'Bug'), ('2', 'Target bug'), ('3', 'False positive'),
                ('4', 'Incompatible marks'), ('5', 'Without marks')
            ], max_length=1
        )),

        migrations.AlterField(model_name='unsafemarkassociationchanges', name='verdict_old', field=models.CharField(
            choices=[
                ('0', 'Uncertainty'), ('1', 'Bug'), ('2', 'Target bug'), ('3', 'False positive'),
                ('4', 'Incompatible marks'), ('5', 'Without marks')
            ], max_length=1
        )),
    ]
