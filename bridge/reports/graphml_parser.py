from xml.dom import minidom


class Attribute:
    def __init__(self, name, value, attr_type="string"):
        self.name = name
        self.value = str(value)
        self.type = attr_type

    def __str__(self):
        return "%s (%s): %s" % (self.name, self.type, str(self.value))


class Item(object):
    ID = 0

    def __init__(self):
        self.id = Item.ID
        Item.ID += 1
        self.attr = {}

    def __str__(self):
        s = "ID: %i\n" % self.id
        for a in self.attr:
            s += "%s : %s\n" % (self.attr[a].name, str(self.attr[a].value))
        return s

    def __setitem__(self, name, value):
        self.attr[name] = Attribute(name, value)

    def __getitem__(self, name):
        return self.attr[name].value

    def attributes(self):
        return self.attr


class Node(Item):
    def __init__(self):
        super(Node, self).__init__()
        self.edges = []

    def edges(self, ):
        return self.edges

    def children(self):
        children = []
        for e in self.edges:
            if e.parent() == self:
                children.append(e.child())
        return children

    def parents(self):
        parents = []
        for e in self.edges:
            if e.child() == self:
                parents.append(e.parent())
        return parents


class Edge(Item):
    def __init__(self, node1, node2, directed=True):
        super(Edge, self).__init__()
        self.node1 = node1
        self.node2 = node2
        self.node1.edges.append(self)
        self.node2.edges.append(self)
        self._directed = directed

    def node(self, node):
        """
        Return the other node
        """
        if node == self.node1:
            return self.node2
        elif node == self.node2:
            return self.node1
        else:
            return None

    def parent(self):
        return self.node1

    def child(self):
        return self.node2

    def directed(self):
        return self._directed

    def set_directed(self, directed):
        self._directed = directed


class Graph:
    def __init__(self):
        self.i = 0
        self._nodes = []
        self._edges = []
        self._root = None
        self._attributes = []
        self.directed = True

    def bfs(self, node=None):
        paths = []
        if node is None:
            if self._root is None:
                return paths
            node = self._root

        path = []
        while len(node.children()) == 1:
            path.append(node)
            node = node.children()[0]
        path.append(node)
        if len(node.children()) == 0:
            paths.append(path)
        else:
            for ch in node.children():
                for p in self.bfs(ch):
                    paths.append(path + p)
        return paths

    def get_depth(self, node):
        depth = 0
        while node.parent() and node != self.root():
            node = node.parent()[0]
            depth += 1

        return depth

    def nodes(self):
        return self._nodes

    def edges(self):
        return self._edges

    def children(self, node):
        self.i = 0
        return node.children()

    def add_node(self, label=""):
        n = Node()
        n['label'] = label
        self._nodes.append(n)
        return n

    def add_edge(self, n1, n2, directed=False):
        if n1 not in self._nodes or n2 not in self._nodes:
            raise ValueError('Specified nodes are not in the graph')
        e = Edge(n1, n2, directed)
        self._edges.append(e)
        return e

    def edge(self, n1, n2):
        for e in self._edges:
            if e.node1 == n1 and e.node2 == n2:
                return e
        return None

    def add_edge_by_label(self, label1, label2):
        n1 = None
        n2 = None
        for n in self._nodes:
            if n['label'] == label1:
                n1 = n
            if n['label'] == label2:
                n2 = n
        if n1 is not None and n2 is not None:
            return self.add_edge(n1, n2)
        else:
            return None

    def set_root(self, node):
        self._root = node

    def root(self):
        return self._root

    def set_root_by_attribute(self, value, attribute='label'):
        for n in self.nodes():
            if n[attribute] == value:
                self.set_root(n)
                return n

    def attributes(self):
        return self._attributes

    def add_attribute(self, name, value, atype='string'):
        self._attributes.append(Attribute(name, value, atype))


class GraphMLParser:
    def __init__(self):
        self.i = 0

    def parse(self, graph):
        self.i = 0
        if isinstance(graph, str):
            dom = minidom.parse(open(graph, 'r', encoding='utf8'))
        elif isinstance(graph, bytes):
            dom = minidom.parseString(graph.decode('utf8'))
        else:
            raise ValueError('Wrong argument: graph. File name or bytes were expected.')
        root = dom.getElementsByTagName("graphml")[0]

        # Get attributes' id, value and type
        edge_attrs = {}
        node_attrs = {}
        graph_attrs = {}
        for attr in root.childNodes:
            if attr.localName == 'key':
                if attr.getAttribute('for') == 'edge':
                    edge_attrs[attr.getAttribute('id')] = {
                        'name': attr.getAttribute('attr.name'),
                        'type': attr.getAttribute('attr.type'),
                    }
                    if attr.firstChild is not None:
                        if len(attr.getElementsByTagName('default')) == 1:
                            if attr.getElementsByTagName('default')[0].firstChild:
                                edge_attrs[attr.getAttribute('id')]['default'] = \
                                    attr.getElementsByTagName('default')[0].firstChild.data
                elif attr.getAttribute('for') == 'node':
                    node_attrs[attr.getAttribute('id')] = {
                        'name': attr.getAttribute('attr.name'),
                        'type': attr.getAttribute('attr.type'),
                    }
                    if attr.firstChild is not None:
                        if len(attr.getElementsByTagName('default')) == 1:
                            if attr.getElementsByTagName('default')[0].firstChild:
                                node_attrs[attr.getAttribute('id')]['default'] = \
                                    attr.getElementsByTagName('default')[0].firstChild.data
                elif attr.getAttribute('for') == 'graph':
                    graph_attrs[attr.getAttribute('id')] = {
                        'name': attr.getAttribute('attr.name'),
                        'type': attr.getAttribute('attr.type'),
                    }
                    if attr.firstChild is not None:
                        if len(attr.getElementsByTagName('default')) == 1:
                            if attr.getElementsByTagName('default')[0].firstChild:
                                graph_attrs[attr.getAttribute('id')]['default'] = \
                                    attr.getElementsByTagName('default')[0].firstChild.data

        graph = root.getElementsByTagName("graph")[0]

        g = Graph()

        for g_attr in graph.childNodes:
            if g_attr.localName == 'data' and g_attr.firstChild is not None:
                if g_attr.getAttribute('key') in graph_attrs:
                    g.add_attribute(graph_attrs[g_attr.getAttribute('key')]['name'],
                                    g_attr.firstChild.data)
                else:
                    g.add_attribute(g_attr.getAttribute('key'), g_attr.firstChild.data)

        # Get nodes
        for node in graph.getElementsByTagName("node"):
            n = g.add_node(node.getAttribute('id'))

            for attr in node.getElementsByTagName("data"):
                attr_key = attr.getAttribute("key")
                if attr.firstChild:
                    if attr_key in node_attrs:
                        n[node_attrs[attr_key]['name']] = attr.firstChild.data
                        n.attr[node_attrs[attr_key]['name']].type = node_attrs[attr_key]['type']
                    else:
                        n[attr_key] = attr.firstChild.data
                else:
                    if attr_key in node_attrs:
                        if 'default' in node_attrs[attr_key]:
                            n[node_attrs[attr_key]['name']] = node_attrs[attr_key]['default']
                        else:
                            n[node_attrs[attr_key]['name']] = ''
                    else:
                        n[attr_key] = ''
            for attr_key in node_attrs:
                if node_attrs[attr_key]['name'] not in n.attr and 'default' in node_attrs[attr_key]:
                    n[node_attrs[attr_key]['name']] = node_attrs[attr_key]['default']
                    n.attr[node_attrs[attr_key]['name']].type = node_attrs[attr_key]['type']

        # Get edges
        for edge in graph.getElementsByTagName("edge"):
            source = edge.getAttribute('source')
            dest = edge.getAttribute('target')
            e = g.add_edge_by_label(source, dest)
            if e is None:
                continue

            for attr in edge.getElementsByTagName("data"):
                attr_key = attr.getAttribute("key")
                if attr.firstChild:
                    if attr_key in edge_attrs:
                        e[edge_attrs[attr_key]['name']] = attr.firstChild.data
                        e.attr[edge_attrs[attr_key]['name']].type = edge_attrs[attr_key]['type']
                    else:
                        e[attr_key] = attr.firstChild.data
                else:
                    if attr_key in edge_attrs:
                        if 'default' in edge_attrs[attr_key]:
                            e[edge_attrs[attr_key]['name']] = edge_attrs[attr_key]['default']
                            e.attr[edge_attrs[attr_key]['name']].type = edge_attrs[attr_key]['type']
                        else:
                            e[edge_attrs[attr_key]['name']] = ''
                    else:
                        e[attr_key] = ''
            for attr_key in edge_attrs:
                if edge_attrs[attr_key]['name'] not in e.attr and 'default' in edge_attrs[attr_key]:
                    e[edge_attrs[attr_key]['name']] = edge_attrs[attr_key]['default']
                    e.attr[edge_attrs[attr_key]['name']].type = edge_attrs[attr_key]['type']

        return g
