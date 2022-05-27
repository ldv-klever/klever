from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('marks', '0003_remove_markunsafehistory_error_trace_and_more'),
    ]

    operations = [
        migrations.AlterField(model_name='marksafe', name='verdict', field=models.CharField(choices=[
            ('0', 'Uncertainty'), ('1', 'Incorrect proof'), ('2', 'Missed target bug')
        ], max_length=1)),

        migrations.AlterField(model_name='marksafehistory', name='verdict', field=models.CharField(choices=[
            ('0', 'Uncertainty'), ('1', 'Incorrect proof'), ('2', 'Missed target bug')
        ], max_length=1)),

        migrations.AlterField(model_name='markunsafe', name='verdict', field=models.CharField(choices=[
            ('0', 'Uncertainty'), ('1', 'Bug'), ('2', 'Target bug'), ('3', 'False positive')
        ], max_length=1)),

        migrations.AlterField(model_name='markunsafehistory', name='verdict', field=models.CharField(choices=[
            ('0', 'Uncertainty'), ('1', 'Bug'), ('2', 'Target bug'), ('3', 'False positive')
        ], max_length=1)),
    ]
