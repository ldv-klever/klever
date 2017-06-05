from __future__ import unicode_literals

import json
from django.db import migrations


def update_views(apps, schema_editor):
    for view in apps.get_model("users", "View").objects.all():
        view_data = json.loads(view.view)
        new_view_data = {}
        if view.type in {'4', '5'}:
            new_view_data['columns'] = view_data['columns']
            if 'order' in view_data and view_data['order'][0] != 'default':
                new_view_data['order'] = [view_data['order'][1], view_data['order'][0]]

            if 'filters' in view_data and 'attr' in view_data['filters']:
                new_view_data['attr'] = [
                    view_data['filters']['attr']['attr'],
                    view_data['filters']['attr']['type'],
                    view_data['filters']['attr']['value']
                ]
        elif view.type == '6':
            new_view_data['columns'] = view_data['columns']
            if 'order' in view_data and view_data['order'][0] != 'component':
                new_view_data['order'] = [view_data['order'][1], view_data['order'][0]]

            if 'filters' in view_data and 'component' in view_data['filters']:
                new_view_data['component'] = [
                    view_data['filters']['component']['type'],
                    view_data['filters']['component']['value']
                ]
            if 'filters' in view_data and 'attr' in view_data['filters']:
                new_view_data['attr'] = [
                    view_data['filters']['attr']['attr'],
                    view_data['filters']['attr']['type'],
                    view_data['filters']['attr']['value']
                ]
        elif view.type == '3':
            if 'order' in view_data:
                if view_data['order'][0] in {'component', 'date'}:
                    new_view_data['order'] = [view_data['order'][0], view_data['order'][1], '']
                else:
                    new_view_data['order'] = ['attr', view_data['order'][1], view_data['order'][0]]

            if 'filters' in view_data and 'component' in view_data['filters']:
                new_view_data['component'] = [
                    view_data['filters']['component']['type'],
                    view_data['filters']['component']['value']
                ]
            if 'filters' in view_data and 'attr' in view_data['filters']:
                new_view_data['attr'] = [
                    view_data['filters']['attr']['attr'],
                    view_data['filters']['attr']['type'],
                    view_data['filters']['attr']['value']
                ]
        elif view.type == '2':
            new_view_data['data'] = view_data['data']

            if 'filters' in view_data:
                to_hide = []
                if 'unknowns_nomark' in view_data['filters'] \
                        and view_data['filters']['unknowns_nomark']['type'] == 'hide':
                    to_hide.append('unknowns_nomark')
                if 'unknowns_total' in view_data['filters'] \
                        and view_data['filters']['unknowns_total']['type'] == 'hide':
                    to_hide.append('unknowns_total')
                if 'resource_total' in view_data['filters'] \
                        and view_data['filters']['resource_total']['type'] == 'hide':
                    to_hide.append('resource_total')
                if len(to_hide) > 0:
                    new_view_data['hidden'] = to_hide

                for filter_name in ['unknown_component', 'unknown_problem',
                                    'resource_component', 'safe_tag', 'unsafe_tag']:
                    if filter_name in view_data['filters']:
                        new_view_data[filter_name] = [
                            view_data['filters'][filter_name]['type'],
                            view_data['filters'][filter_name]['value']
                        ]
                if 'stat_attr_name' in view_data['filters']:
                    new_view_data['attr_stat'] = [view_data['filters']['stat_attr_name']['value']]
                if 'attr' in view_data['filters']:
                    new_view_data['attr_stat_filter'] = [
                        view_data['filters']['attr']['type'],
                        view_data['filters']['attr']['value']
                    ]
        elif view.type == '9':
            new_view_data['columns'] = view_data['columns']
            if 'order' in view_data and view_data['order'] == 'num_of_links':
                new_view_data['order'] = ['num_of_links']

            if 'filters' in view_data:
                for filter_name in ['status', 'component', 'source']:
                    if filter_name in view_data['filters']:
                        new_view_data[filter_name] = [
                            view_data['filters'][filter_name]['type'],
                            view_data['filters'][filter_name]['value']
                        ]
                if 'author' in view_data['filters']:
                    new_view_data['author'] = [view_data['filters']['author']['value']]
        elif view.type in {'7', '8'}:
            new_view_data['columns'] = view_data['columns']
            if 'order' in view_data:
                if view_data['order'] == 'num_of_links':
                    new_view_data['order'] = ['num_of_links', '']
                else:
                    new_view_data['order'] = ['attr', view_data['order']]

            if 'filters' in view_data:
                for filter_name in ['status', 'verdict', 'source']:
                    if filter_name in view_data['filters']:
                        new_view_data[filter_name] = [
                            view_data['filters'][filter_name]['type'],
                            view_data['filters'][filter_name]['value']
                        ]
                if 'author' in view_data['filters']:
                    new_view_data['author'] = [view_data['filters']['author']['value']]
                if 'attr' in view_data['filters']:
                    new_view_data['attr'] = [
                        view_data['filters']['attr']['attr'],
                        view_data['filters']['attr']['type'],
                        view_data['filters']['attr']['value']
                    ]
        elif view.type == '1':
            new_view_data['columns'] = view_data['columns']
            if 'orders' in view_data:
                for order_val in view_data['orders']:
                    order_type = 'down'
                    if order_val.startswith('-'):
                        order_val = order_val[1:]
                        order_type = 'up'
                    if order_val == 'date':
                        new_view_data['order'] = [order_type, 'date']
                        break
                    elif order_val == 'name':
                        new_view_data['order'] = [order_type, 'title']
                        break
                    elif order_val == 'start_date':
                        new_view_data['order'] = [order_type, 'start']
                        break
                    elif order_val == 'finish_date':
                        new_view_data['order'] = [order_type, 'finish']
                        break
            if 'filters' in view_data:
                if 'name' in view_data['filters']:
                    new_view_data['title'] = [
                        view_data['filters']['name']['type'], view_data['filters']['name']['value']
                    ]
                if 'change_date' in view_data['filters']:
                    (measure, value) = view_data['filters']['change_date']['value'].split(':', 1)
                    new_view_data['change_date'] = [view_data['filters']['change_date']['type'], value, measure]
                if 'status' in view_data['filters']:
                    new_view_data['status'] = view_data['filters']['status']['value']
                if 'finish_date' in view_data['filters']:
                    (month, year) = view_data['filters']['finish_date']['value'].split(':', 1)
                    new_view_data['change_date'] = [view_data['filters']['finish_date']['type'], month, year]
                for filter_name in ['change_author', 'resource_component', 'problem_component',
                                    'problem_problem', 'format', 'priority']:
                    if filter_name in view_data['filters']:
                        new_view_data[filter_name] = [
                            view_data['filters'][filter_name]['type'],
                            view_data['filters'][filter_name]['value']
                        ]
        view.view = json.dumps(new_view_data)
        view.save()


class Migration(migrations.Migration):
    dependencies = [('users', '0004_auto_20170530_1428')]
    operations = [migrations.RunPython(update_views)]