from django.contrib.humanize.templatetags.humanize import naturaltime

from rest_framework.fields import DateTimeField

from bridge.vars import DATAFORMAT


class NaturalDateTimeField(DateTimeField):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.format = 'r'

    def to_internal_value(self, value):
        if not value:
            return None
        if self.root and hasattr(self.root, 'context') and 'request' in self.root.context:
            user = self.root.context['request'].user
            if user.is_authenticated and user.data_format == DATAFORMAT[1][0]:
                return naturaltime(value)

        output_format = getattr(self, 'format', api_settings.DATETIME_FORMAT)

        if output_format is None or isinstance(value, six.string_types):
            return value

        value = self.enforce_timezone(value)

        if output_format.lower() == ISO_8601:
            value = value.isoformat()
            if value.endswith('+00:00'):
                value = value[:-6] + 'Z'
            return value
        return value.strftime(output_format)
