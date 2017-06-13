from __future__ import unicode_literals

import json
from django.db import migrations


def update_views(apps, schema_editor):
    for view in apps.get_model("users", "View").objects.filter(type__in='45'):
        view_data = json.loads(view.view)

        if 'order' in view_data and view_data['order'][0] != 'default':
            view_data['order'] = [view_data['order'][0], 'attr', view_data['order'][1]]
            view.view = json.dumps(view_data)
            view.save()


class Migration(migrations.Migration):
    dependencies = [('users', '0008_auto_20170612_1823')]
    operations = [migrations.RunPython(update_views)]