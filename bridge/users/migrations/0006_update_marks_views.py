from __future__ import unicode_literals

import json
from django.db import migrations


def update_views(apps, schema_editor):
    for view in apps.get_model("users", "View").objects.filter(type__in={'7', '8', '9'}):
        view_data = json.loads(view.view)
        if view.type == '9':
            if 'order' not in view_data:
                view_data['order'] = ['up', 'change_date']
            else:
                view_data['order'] = ['down', view_data['order'][0]]
        elif view.type in {'7', '8'}:
            if 'order' not in view_data:
                view_data['order'] = ['up', 'change_date', '']
            else:
                view_data['order'] = ['down', view_data['order'][0], view_data['order'][1]]
        view.view = json.dumps(view_data)
        view.save()


class Migration(migrations.Migration):
    dependencies = [('users', '0005_update_views')]
    operations = [migrations.RunPython(update_views)]