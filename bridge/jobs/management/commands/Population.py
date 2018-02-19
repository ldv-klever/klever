from django.core.management.base import BaseCommand, CommandError

from bridge.populate import Population


class Command(BaseCommand):
    help = 'Populates jobs and marks.'

    def handle(self, *args, **options):
        try:
            Population()
        except Exception as e:
            raise CommandError(str(e))
        self.stdout.write(self.style.SUCCESS('Population was successfully finished'))
