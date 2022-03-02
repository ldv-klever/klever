from django.db import migrations

from bridge.vars import USER_ROLES


def update_admin(apps, schema_editor):
    User = apps.get_model('users', 'User')
    User.objects.filter(is_staff=True).update(role=USER_ROLES[2][0])
    User.objects.filter(is_superuser=True).update(role=USER_ROLES[2][0])


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0002_user_notes_level'),
    ]

    operations = [
        migrations.RunPython(update_admin),
    ]
