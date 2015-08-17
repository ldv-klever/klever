from django.utils.translation import ugettext as _, activate
from urllib.parse import unquote
from django.shortcuts import render


def omega_error(request, err_code=0, user_message=None):
    if request.user.is_authenticated():
        activate(request.user.extended.language)
    else:
        activate(request.LANGUAGE_CODE)

    err_code = int(err_code)
    message = _('Unknown error')
    back = None
    if request.method == 'GET':
        back = request.GET.get('back', None)
        if back is not None:
            back = unquote(back)
    if err_code == 444:
        message = _("The page was not found")
    elif err_code == 404:
        message = _('The job was not found')
    elif err_code == 400:
        message = _("You don't have an access to this job")
    elif err_code == 450:
        message = _('Some job is downloaded right now, '
                    'please try again later')
    elif err_code == 451:
        message = _('Wrong parameters, please reload page and try again.')
    elif err_code == 504:
        message = _('The report was not found')
    elif err_code == 604:
        message = _("The mark was not found")
    if isinstance(user_message, str):
        message = user_message
    return render(request, 'error.html', {'message': message, 'back': back})
