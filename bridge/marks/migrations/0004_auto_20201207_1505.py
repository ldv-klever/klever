from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('marks', '0003_fullname')]

    operations = [
        migrations.AlterField(
            model_name='safetag', name='name', field=models.CharField(db_index=True, max_length=1024, unique=True)
        ),
        migrations.AlterField(
            model_name='unsafetag', name='name', field=models.CharField(db_index=True, max_length=1024, unique=True)
        ),
    ]
