from __future__ import unicode_literals

import json
from django.db import migrations


def update_views(apps, schema_editor):
    for view in apps.get_model("users", "View").objects.filter(type__in={'10', '11', '12'}):
        view_data = json.loads(view.view)
        new_columns = []
        changed = False
        for col in view_data['columns']:
            if col == 'mark_type':
                new_columns.append('source')
                changed = True
            else:
                new_columns.append(col)
        if changed:
            view_data['columns'] = new_columns
            view.view = json.dumps(view_data)
            view.save()


class Migration(migrations.Migration):
    dependencies = [('users', '0009_update_unsafes_views')]
    operations = [migrations.RunPython(update_views)]