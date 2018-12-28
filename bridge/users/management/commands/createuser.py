from django.core.management.base import BaseCommand, CommandError

from rest_framework import serializers

from bridge.vars import USER_ROLES
from users.models import User
from users.serializers import ManageUserSerializer


class Command(BaseCommand):
    help = 'Used to create a user. If user with specified username exists then it will be updated with provided data.'
    requires_migrations_checks = True

    def add_arguments(self, parser):
        role_choices = list(x[0] for x in USER_ROLES)
        parser.add_argument('--username', dest='username', help='Specifies the username.')
        parser.add_argument('--password', dest='password', help='Specifies the password.')
        parser.add_argument('--role', choices=role_choices, default=role_choices[0])
        parser.add_argument('--staff', dest='is_staff', action='store_true', help='Is user a staff?')
        parser.add_argument('--superuser', dest='is_superuser', action='store_true', help='Is user a superuser?')

    def handle(self, *args, **options):
        # If user with specified username exists, then update its password and role
        user = User.objects.filter(username=options['username']).first()

        serializer = ManageUserSerializer(instance=user, data=options)
        try:
            serializer.is_valid(raise_exception=True)
        except serializers.ValidationError as e:
            raise CommandError(str(e))
        serializer.save()

        if options['verbosity'] >= 1:
            self.stdout.write("User created successfully.")
