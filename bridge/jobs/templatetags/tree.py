from collections import defaultdict
from django import template

register = template.Library()


class TreeNode(template.Node):
    def __init__(self, node_list, tree_dict, parent_attr, ordering_attr, item_icon_class):
        self.node_list = node_list
        self.tree = tree_dict
        self.parent_attr = parent_attr
        self.ordering_attr = ordering_attr
        self.icon = item_icon_class

    def pairs(self, tree_dict):
        parent_map = defaultdict(list)
        for item_id, item_data in tree_dict.items():
            parent_id = item_data[self.parent_attr]
            item_data['_tree_item_id_'] = item_id
            parent_map[parent_id].append(item_data)

        def tree_level(parent):
            for child in sorted(parent_map[parent], key=lambda x: x[self.ordering_attr]):
                yield child, list(tree_level(child['_tree_item_id_']))

        return list(tree_level(None))

    def render_items(self, items, level):
        if not items:
            return ''
        return '<div class="ui list">{}</div>'.format(''.join(list(
            self.render_item(item, sub_items, level) for item, sub_items in items
        )))

    def render_item(self, item, sub_items, level):
        if not item:
            return ''
        return ''.join([
            '<div class="item">',
            '<i class="{} icon"></i>'.format(self.icon),
            '<div class="content">{}{}</div>'.format(
                self.node_list.render(template.Context({'item': item, 'level': level})),
                self.render_items(sub_items, level + 1)
            ),
            '</div>'
        ])

    def render(self, context):
        tree_list = self.pairs(self.tree.resolve(context))
        return self.render_items(tree_list, 0)


@register.tag
def tree(parser, token):
    try:
        tag_name, tree_items, parent_attr, ordering_attr, icon_class = token.split_contents()
    except ValueError:
        raise template.TemplateSyntaxError('%r tag requires exactly three arguments: '
                                           'dict of items, parent attribute and icon class' % token.contents.split()[0])
    node_list = parser.parse('end' + tag_name)
    parser.delete_first_token()
    return TreeNode(
        node_list,
        parser.compile_filter(tree_items),
        parent_attr[1:-1],
        ordering_attr[1:-1],
        icon_class[1:-1]
    )
