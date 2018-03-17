import json

from django.core.management.base import BaseCommand, CommandError

from bridge.populate import populate_users


class Command(BaseCommand):
    help = """
Populates administrator, manager and service users.
Accept three optional arguments: 'admin', 'manager', 'service' in json format.
Example argument: '{"username": "uname", "password": "pass", "last_name": "Name1", "first_name": "Name2"}'.
'last_name' and 'first_name' are not required; 'username' and 'password' are required. 'email' can be set for admin.
    """

    def add_arguments(self, parser):
        parser.add_argument('--admin', dest='admin', help='Administrator data in json format')
        parser.add_argument('--manager', dest='manager', help='Manager data in json format')
        parser.add_argument('--service', dest='service', help='Service data in json format')

    def handle(self, *args, **options):
        users = {'admin': None, 'manager': None, 'service': None}
        if 'admin' in options and options['admin'] is not None:
            users['admin'] = json.loads(options['admin'])
        if 'manager' in options and options['manager'] is not None:
            users['manager'] = json.loads(options['manager'])
        if 'service' in options and options['service'] is not None:
            users['service'] = json.loads(options['service'])
        try:
            res = populate_users(**users)
        except Exception as e:
            raise CommandError(str(e))
        if res is not None:
            raise CommandError(res)
        self.stdout.write(self.style.SUCCESS('Users were successfully created'))
