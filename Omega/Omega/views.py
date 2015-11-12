from django.utils.translation import ugettext as _, activate
from urllib.parse import unquote
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from Omega.populate import Population
from Omega.vars import ERRORS, USER_ROLES
from users.models import Extended


def omega_error(request, err_code=0, user_message=None):
    if request.user.is_authenticated():
        activate(request.user.extended.language)
    else:
        activate(request.LANGUAGE_CODE)

    err_code = int(err_code)

    back = None
    if request.method == 'GET':
        back = request.GET.get('back', None)
        if back is not None:
            back = unquote(back)

    if isinstance(user_message, str):
        message = user_message
    else:
        if err_code in ERRORS:
            message = ERRORS[err_code]
        else:
            message = _('Unknown error')

    return render(request, 'error.html', {'message': message, 'back': back})


@login_required
def population(request):
    if request.method == 'POST':
        manager_username = request.POST.get('manager_username', None)
        if not(isinstance(manager_username, str) and len(manager_username) > 0):
            manager_username = None
        service_username = request.POST.get('service_username', None)
        if not(isinstance(service_username, str) and len(service_username) > 0):
            service_username = None
        popul = Population(request.user, manager_username, service_username)
        return render(request, 'Population.html', {'population': popul})
    return render(request, 'Population.html', {
        'need_manager': (len(Extended.objects.filter(role=USER_ROLES[2][0])) == 0),
        'need_service': (len(Extended.objects.filter(role=USER_ROLES[4][0])) == 0),
    })
