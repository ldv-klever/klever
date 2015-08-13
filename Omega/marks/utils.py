from datetime import datetime
import hashlib
from django.core.exceptions import ObjectDoesNotExist
from reports.models import AttrName
from marks.models import *


def run_function(func, *args):
    if isinstance(func, MarkUnsafeCompare):
        new_func = "def mark_unsafe_compare(pattern_error_trace, error_trace):"
    elif isinstance(func, MarkUnsafeConvert):
        new_func = "def mark_unsafe_convert(error_trace):"
    else:
        return None
    new_func += '\n    '.join(func.body.split('\n'))
    d = {}
    exec(new_func, d)
    return d[func.name](args)


class NewMark(object):

    def __init__(self, inst, user, mark_type, args):
        """
        After initialization has params: mark, mark_version and error:
        mark - Instance of created/changed MarkUnsafe/MarkSafe
        mark_version - instance of MarkUnsafeHistory/MarkSafeHistory,
                       last version for mark
        error - error message in case of failure, None if everything is OK
        user - User instance of mark author
        :param inst: instance of ReportUnsafe/ReportSafe for creating mark
        and insatnce of MarkUnsafe/MarkSafe for changing it
        :param user: instance of User (author of mark change/creation)
        :param mark_type: 'safe' or 'unsafe'
        :param args: dictionary with keys:
            'status': see MARK_STATUS from Omega.vars, default - '0'.
            'verdict': see MARK_UNSAFE/MARK_SAFE from Omega.vars, default - '0'
            'convert_id': MarkUnsafeCompare id (only for creating unsafe mark)
            'compare_id': MarkUnsafeConvert id (only for unsafe mark)
            'attrs': list of dictionaries with required keys:
                    'attr': name of attribute (string)
                    'value': value of attribute (string)
                    'is_compare': True of False
            'is_modifiable': True or False, default - True
                            (only for creating mark)
        :return: Nothing
        """
        self.mark = None
        self.mark_version = None
        self.user = user
        self.type = mark_type
        if self.type != 'safe' or self.type != 'unsafe':
            self.error = "Wrong mark type"
        elif not isinstance(args, dict) or not isinstance(user, User):
            self.error = "Wrong parameters"
        elif self.type == 'safe' and isinstance(inst, ReportSafe) or \
                self.type == 'unsafe' and isinstance(inst, ReportUnsafe):
            self.error = self.__create_mark(inst, args)
        elif self.type == 'safe' and isinstance(inst, MarkUnsafe) or \
                self.type == 'unsafe' and isinstance(inst, MarkSafe):
            self.error = self.__change_mark(inst, args)
        else:
            self.error = "Wrong parameters"

    def __create_mark(self, report, args):
        mark = MarkUnsafe()
        mark.author = self.user

        if self.type == 'unsafe':
            if 'convert_id' in args:
                try:
                    func = MarkUnsafeConvert.objects.get(
                        pk=int(args['convert_id']))
                    converted = run_function(func, report.error_trace)
                    if converted is not None and len(converted) > 0:
                        mark.error_trace = converted
                    else:
                        return "Error in converting trace"
                except ObjectDoesNotExist:
                    return "Convertion function was not found"

            if 'compare_id' in args:
                try:
                    mark.function = MarkUnsafeCompare.objects.get(
                        pk=int(args['compare_id']))
                except ObjectDoesNotExist:
                    return "Comparison function was not found"
        mark.format = report.root.job.format
        mark.type = report.root.job.type

        time_encoded = datetime.now().strftime("%Y%m%d%H%M%S%f%z").\
            encode('utf8')
        mark.identifier = hashlib.md5(time_encoded).hexdigest()

        if 'is_modifiable' in args and isinstance(args['is_modifiable'], bool):
            mark.is_modifiable = args['is_modifiable']

        if 'verdict' in args:
            if self.type == 'unsafe' and \
                    args['verdict'] in list(x[0] for x in MARK_UNSAFE):
                mark.verdict = args['verdict']
            elif args['verdict'] in list(x[0] for x in MARK_SAFE):
                mark.verdict = args['verdict']

        if 'status' in args and \
                args['status'] in list(x[0] for x in MARK_STATUS):
            mark.status = args['status']

        mark.save()
        self.__update_mark(mark)
        if 'attrs' in args:
            res = self.__update_attributes(args['attrs'])
            if res is not None:
                mark.delete()
                return res
        self.mark = mark
        return None

    def __change_mark(self, mark, args):
        if not mark.is_modifiable:
            return "Mark is not modifiable"
        mark.author = self.user

        if self.type == 'unsafe' and 'compare_id' in args:
            try:
                mark.function = MarkUnsafeCompare.objects.get(
                    pk=int(args['compare_id']))
            except ObjectDoesNotExist:
                return "Comparison function was not found"

        if 'verdict' in args:
            if self.type == 'unsafe' and \
                    args['verdict'] in list(x[0] for x in MARK_UNSAFE):
                mark.verdict = args['verdict']
            elif args['verdict'] in list(x[0] for x in MARK_SAFE):
                mark.verdict = args['verdict']

        if 'status' in args and \
                args['status'] in list(x[0] for x in MARK_STATUS):
            mark.status = args['status']

        mark.version += 1
        mark.save()
        self.__update_mark(mark)
        if 'attrs' in args:
            res = self.__update_attributes(args['attrs'])
            if res is not None:
                mark.version -= 1
                mark.save()
                self.mark_version.delete()
                return res
        self.mark = mark
        return None

    def __update_mark(self, mark, comment=''):
        if self.type == 'unsafe':
            new_version = MarkUnsafeHistory()
        else:
            new_version = MarkSafeHistory()

        new_version.mark = mark
        if self.type == 'unsafe':
            new_version.function = mark.function
        new_version.verdict = mark.verdict
        new_version.version = mark.version
        new_version.status = mark.status
        new_version.change_data = mark.change_date
        new_version.comment = comment
        new_version.author = mark.author
        new_version.save()
        self.mark_version = new_version

    def __update_attributes(self, attrs):
        if not isinstance(attrs, list):
            return 'Wrong attributes'
        for a in attrs:
            if not isinstance(a, dict) or \
                    any(x in a for x in ['attr', 'value', 'is_compare']):
                return 'Wrong args'
        for a in attrs:
            attr_name = AttrName.objects.get_or_create(name=a['attr'])
            attr = Attr.objects.get_or_create(name=attr_name, value=a['value'])
            if self.type == 'unsafe':
                mark_attr = MarkUnsafeAttr.objects.get_or_create(
                    mark=self.mark_version, attr=attr
                )
            else:
                mark_attr = MarkSafeAttr.objects.get_or_create(
                    mark=self.mark_version, attr=attr
                )
            mark_attr.is_compare = a['is_compare']
            try:
                mark_attr.save()
            except ValueError:
                return "Wrong attributes"
        return None
