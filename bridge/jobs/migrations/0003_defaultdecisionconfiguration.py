from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('jobs', '0002_auto_20210906_1842'),
    ]

    operations = [
        migrations.CreateModel(name='DefaultDecisionConfiguration', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('file', models.ForeignKey(on_delete=models.deletion.CASCADE, to='jobs.JobFile')),
            ('user', models.OneToOneField(
                on_delete=models.deletion.CASCADE, related_name='decision_conf', to=settings.AUTH_USER_MODEL
            )),
        ], options={'db_table': 'jobs_default_decision_conf'}),
    ]
