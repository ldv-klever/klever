from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from bridge.vars import SAFE_VERDICTS, UNSAFE_VERDICTS, MARK_UNSAFE, UNSAFE_STATUS


def safe_color(verdict=None, inverted=False):
    if not verdict:
        return None
    # SAFE_VERDICTS
    if verdict == '0':
        # Unknown - Purple
        return inverted and '#cb58ec' or '#930BBD'
    if verdict == '1':
        # Incorrect proof - Orange
        return inverted and '#FF8533' or '#D05A00'
    if verdict == '2':
        # Missed target bug - Orange
        return inverted and '#e81919' or '#C70646'
    if verdict == '3':
        # Incompatible - Red
        return inverted and '#e81919' or '#C70646'
    # Without marks - Default color
    return None


def unsafe_color(verdict=None, inverted=False):
    if not verdict:
        return None
    # UNSAFE_VERDICTS
    if verdict == '0':
        # Unknown - Purple
        return inverted and '#cb58ec' or '#930BBD'
    if verdict == '1':
        # Bug - Red
        return inverted and '#e81919' or '#C70646'
    if verdict == '2':
        # Target bug - Red
        return inverted and '#e81919' or '#C70646'
    if verdict == '3':
        # False positive - Orange
        return inverted and '#FF8533' or '#D05A00'
    if verdict == '4':
        # Incompatible - Red
        return inverted and '#e81919' or '#C70646'
    # Without marks - Default color
    return None


def bug_status_color(status=None):
    if not status:
        return None
    # UNSAFE_STATUS
    if status == '0':
        # Unreported - red
        return '#e81919'
    if status == '1':
        # Reported - orange
        return '#FF8533'
    if status == '2':
        # Reported - orange
        return '#FF8533'
    if status == '3':
        # Rejected - green
        return '#00c600'
    # Incompatible marks - red
    return '#e81919'


def safe_verdicts_sum(*args):
    result = SAFE_VERDICTS[4][0]
    for verdict in args:
        if result == SAFE_VERDICTS[4][0]:
            # No marks + X = X
            result = verdict
        elif verdict == SAFE_VERDICTS[4][0]:
            # X + No marks = X
            continue
        elif result != verdict:
            # V1 + V2 = Incompatible
            result = SAFE_VERDICTS[3][0]
        else:
            # X + X = X
            continue
    return result


def unsafe_verdicts_sum(*args):
    result = UNSAFE_VERDICTS[5][0]
    for verdict in args:
        if result == UNSAFE_VERDICTS[5][0]:
            # No marks + X = X
            result = verdict
        elif verdict == UNSAFE_VERDICTS[5][0]:
            # X + No marks = X
            continue
        elif result != verdict:
            # V1 + V2 = Incompatible
            result = UNSAFE_VERDICTS[4][0]
        else:
            # X + X = X
            continue
    return result


class BugStatusCollector:
    def __init__(self):
        self._incompatible = set()
        self._statuses = {}

    def add(self, report_id, mark_verdict, mark_status):
        if report_id in self._incompatible:
            return
        if mark_verdict == MARK_UNSAFE[1][0]:
            self._statuses.setdefault(report_id, mark_status)
            if self._statuses[report_id] != mark_status:
                self._incompatible.add(report_id)
                self._statuses.pop(report_id)
        elif report_id in self._statuses:
            self._incompatible.add(report_id)
            self._statuses.pop(report_id)

    @property
    def result(self):
        result_data = {}
        for report_id in self._incompatible:
            result_data[report_id] = UNSAFE_STATUS[4][0]
        for report_id, status in self._statuses.items():
            result_data[report_id] = status
        self._incompatible = set()
        self._statuses = {}
        return result_data

    @classmethod
    def sum(cls, old_status, new_status, new_verdict):
        if old_status is None and new_status is None:
            # WithoutMarks + NotABug = WithoutBugs + NotABug = WithoutBugs
            return None
        if new_status is None:
            # Bug + NotABug = Incompatible marks
            return UNSAFE_STATUS[4][0]
        if old_status is None:
            if new_verdict == UNSAFE_VERDICTS[4][0]:
                # WithoutBugs + Bug = Incombatible marks
                return UNSAFE_STATUS[4][0]
            # WithoutMarks + Bug = Bug
            return new_status
        if old_status == new_status:
            # Bug + Bug = Bug
            return new_status
        # Bug1 + Bug2 = Incompatible marks
        return UNSAFE_STATUS[4][0]


class SafeColumns:
    total_name = 'total'
    manual_name = 'manual'
    automatic_name = 'automatic'

    def __init__(self, detailed=False, prefix='safe'):
        self._detailed = detailed
        self.prefix = prefix

    def extend_column(self, base_column):
        if not self._detailed:
            return [base_column]

        # Do not extend safes without marks
        verdict = base_column.split(':')[-1]
        if verdict in {SAFE_VERDICTS[4][0], self.total_name}:
            return [base_column]

        return [
            '{}:{}'.format(base_column, self.manual_name),
            '{}:{}'.format(base_column, self.automatic_name)
        ]

    @property
    def available(self):
        available_columns = []
        for v in SAFE_VERDICTS:
            available_columns.extend(self.extend_column('{}:{}'.format(self.prefix, v[0])))
        return available_columns + ['{}:{}'.format(self.prefix, self.total_name)]

    @cached_property
    def titles(self):
        titles_map = (
            (SAFE_VERDICTS[0][0], _('Uncertainties')),
            (SAFE_VERDICTS[1][0], _('Missed target bugs')),
            (SAFE_VERDICTS[2][0], _('Incorrect proof')),
            (SAFE_VERDICTS[3][0], _('Incompatible marks')),
            (SAFE_VERDICTS[4][0], _('To be assessed')),  # Without marks
            (self.total_name, _('Total'))
        )

        titles = dict(('{}:{}'.format(self.prefix, col), title) for col, title in titles_map)
        if self._detailed:
            for v in SAFE_VERDICTS[:4]:
                titles[':'.join([self.prefix, v[0], self.manual_name])] = _('Manually assessed')
                titles[':'.join([self.prefix, v[0], self.automatic_name])] = _('Automatically assessed')
        return titles

    def get_verdict_column(self, verdict=None, manual=None):
        if verdict is None:
            return '{}:{}'.format(self.prefix, self.total_name)
        if manual is None:
            return '{}:{}'.format(self.prefix, verdict)
        return ':'.join([self.prefix, verdict, manual and self.manual_name or self.automatic_name])

    def is_detailed(self, verdict):
        return self._detailed and verdict and verdict != SAFE_VERDICTS[4][0]


class UnsafeColumns:
    total_name = 'total'
    manual_name = 'manual'
    automatic_name = 'automatic'

    def __init__(self, detailed=False, prefix='unsafe'):
        self._detailed = detailed
        self.prefix = prefix

    def extend_column(self, base_column):
        if not self._detailed:
            return [base_column]

        # Do not extend unsafes without marks
        verdict = base_column.split(':')[-1]
        if verdict in {UNSAFE_VERDICTS[5][0], self.total_name}:
            return [base_column]

        return [
            '{}:{}'.format(base_column, self.manual_name),
            '{}:{}'.format(base_column, self.automatic_name)
        ]

    @property
    def available(self):
        available_columns = []
        for v in UNSAFE_VERDICTS:
            available_columns.extend(self.extend_column('{}:{}'.format(self.prefix, v[0])))
        return available_columns + ['{}:{}'.format(self.prefix, self.total_name)]

    @cached_property
    def titles(self):
        titles_map = (
            (UNSAFE_VERDICTS[0][0], _('Uncertainties')),
            (UNSAFE_VERDICTS[1][0], _('Bugs')),
            (UNSAFE_VERDICTS[2][0], _('Target bugs')),
            (UNSAFE_VERDICTS[3][0], _('False positives')),
            (UNSAFE_VERDICTS[4][0], _('Incompatible marks')),
            (UNSAFE_VERDICTS[5][0], _('To be assessed')),  # Without marks
            (self.total_name, _('Total'))
        )

        titles = dict(('{}:{}'.format(self.prefix, col), title) for col, title in titles_map)
        if self._detailed:
            for v in UNSAFE_VERDICTS[:5]:
                titles[':'.join([self.prefix, v[0], self.manual_name])] = _('Manually assessed')
                titles[':'.join([self.prefix, v[0], self.automatic_name])] = _('Automatically assessed')
        return titles

    def get_verdict_column(self, verdict=None, manual=None):
        if verdict is None:
            return '{}:{}'.format(self.prefix, self.total_name)
        if manual is None:
            return '{}:{}'.format(self.prefix, verdict)
        return ':'.join([self.prefix, verdict, manual and self.manual_name or self.automatic_name])

    def is_detailed(self, verdict):
        return self._detailed and verdict and verdict != UNSAFE_VERDICTS[5][0]
