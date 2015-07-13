from django.utils.translation import ugettext as _

FORMAT = 1

JOB_CLASSES = (
    ('0', _('Verification of Linux kernel modules')),
    ('1', _('Verification of commits to Linux kernel Git repositories')),
    ('2', _('Verification of C programs')),
)

JOB_ROLES = (
    ('0', _('No access')),
    ('1', _('Observer')),
    ('2', _('Expert')),
    ('3', _('Observer and Operator')),
    ('4', _('Expert and Operator')),
)

# Default view of the table
JOB_DEF_VIEW = {
    'columns': ['name', 'version', 'parent_name', 'role', 'author', 'date',
                'status', 'unsafe', 'safe', 'problem', 'resource'],
    # Available orders: ['date', 'status', 'name', 'author']
    'orders': ['-date'],

    # Available filters (id [types], (example value)):
    # name [iexact, istartswith, icontains] (<any text>)
    # change_author [is] (<id in the table>)
    # change_date [younger, older] (weeks|days|hours|minutes: <number>)
    # status [is, isnot] (<status identifier>)
    # resource:component [iexact, istartswith, icontains] (<any text>)
    # problem:component [iexact, istartswith, icontains] (<any text>)
    # problem:problem [iexact, istartswith, icontains] (<any text>)
    # format [is] (<number>)
    'filters': {
        # 'name': {
        #     'type': 'istartswith',
        #     'value': 'Title of the job',
        # },
        # 'change_author': {
        #     'type': 'is',
        #     'value': '1',
        # },
        # 'change_date': {
        #     'type': 'younger',
        #     'value': 'weeks:2',
        # },
        # 'resource_component': {
        #     'type': 'istartswith',
        #     'value': 'D',
        # },
        # 'problem_problem': {
        #     'type': 'icontains',
        #     'value': '1',
        # },
        # 'format': {
        #     'type': 'is',
        #     'value': '1',
        # },
    },
}
