from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('users', '0001_initial')]

    operations = [
        migrations.AddField(model_name='user', name='notes_level', field=models.PositiveIntegerField(
            default=2, help_text='Error trace notes with level higher than selected one will be ignored',
            verbose_name='Error trace notes level'
        )),
    ]
