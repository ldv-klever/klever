TEST_NODES_DATA = [
    {
        'CPU model': 'string',
        'CPU number': 8,
        'RAM memory': 16000000000,
        'disk memory': 300000000000,
        'nodes': {
            'viro.intra.ispras.ru': {
                'status': 'HEALTHY',
                'workload': {
                    'reserved CPU number': 4,
                    'reserved RAM memory': 8000000000,
                    'reserved disk memory': 200000000000,
                    'running verification tasks': 2,
                    'running verification jobs': 2,
                    'available for jobs': True,
                    'available for tasks': True
                }
            },
            'cox.intra.ispras.ru': {
                'status': 'DISCONNECTED'
            }
        }
    },
    {
        'CPU model': 'string',
        'CPU number': 8,
        'RAM memory': 64000000000,
        'disk memory': 1000000000000,
        'nodes': {
            'kent.intra.ispras.ru': {
                'status': 'AILING',
                'workload': {
                    'reserved CPU number': 6,
                    'reserved RAM memory': 20000000000,
                    'reserved disk memory': 500000000000,
                    'running verification tasks': 96,
                    'running verification jobs': 0,
                    'available for jobs': False,
                    'available for tasks': True
                }
            },
            'morton.intra.ispras.ru': {
                'status': 'HEALTHY',
                'workload': {
                    'reserved CPU number': 0,
                    'reserved RAM memory': 0,
                    'reserved disk memory': 0,
                    'running verification tasks': 0,
                    'running verification jobs': 0,
                    'available for jobs': True,
                    'available for tasks': True
                }
            },
        }
    },
]

TEST_TOOLS_DATA = [
    {
        'tool': 'BLAST',
        'version': '2.7.2'
    },
    {
        'tool': 'CPAchecker',
        'version': '1.1.1'
    }
]

TEST_JSON = {
    'tasks': {
        'pending': [],
        'processing': [],
        'finished': [],
        'error': []
    },
    'task errors': {},
    'task descriptions': {},
    'task solutions': {},
    'jobs': {
        'pending': [],
        'processing': [],
        'finished': [],
        'error': [],
        'cancelled': []
    },
    'job errors': {},
    'Job configurations': {}
}
