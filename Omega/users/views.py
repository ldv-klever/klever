from django.shortcuts import render
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse
from users.forms import UserExtendedForm, UserForm, EditUserForm
import pytz
from django.contrib.auth.decorators import login_required
from django.forms import ValidationError


def user_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(username=username, password=password)
        if user:
            if user.is_active:
                login(request, user)
                return HttpResponseRedirect(reverse('users:index'))
            else:
                login_error = "Your account is disabled!"
        else:
            login_error = "Invalid login details supplied."
        return render(request, 'users/login.html',
                      {'login_errors': login_error})
    else:
        return render(request, 'users/login.html')


def user_logout(request):
    logout(request)
    return HttpResponseRedirect(reverse('users:index'))


def index(request):
    context = {}
    if request.user.is_authenticated():
        context['chdate'] = request.user.extended.change_date
        user_tz = request.user.extended.timezone
        if len(user_tz) > 0:
            context['user_tz'] = user_tz
    return render(request, 'users/index.html', context)


def register(request):
    registered = False

    if request.method == 'POST':
        user_form = UserForm(data=request.POST)
        profile_form = UserExtendedForm(data=request.POST)
        user_tz = request.POST.get('timezone')
        if user_form.is_valid() and profile_form.is_valid():
            user = user_form.save()
            user.set_password(user.password)
            profile = profile_form.save(commit=False)
            profile.user = user
            profile.change_author = user

            if user_tz:
                profile.timezone = user_tz
            # if 'picture' in request.FILES:
            #    profile.picture = request.FILES['picture']

            try:
                profile.save()
            except:
                raise ValidationError("Can't save user to the database!")
            user.save()
            registered = True
        else:
            print(user_form.errors, profile_form.errors)
    else:
        user_form = UserForm()
        profile_form = UserExtendedForm()

    return render(request, 'users/register.html',
                  {
                      'user_form': user_form,
                      'profile_form': profile_form,
                      'registered': registered,
                      'timezones': pytz.common_timezones,
                  })


@login_required
def edit_profile(request):
    changed = False

    if request.method == 'POST':
        user_form = EditUserForm(data=request.POST, request=request,
                                 instance=request.user)
        profile_form = UserExtendedForm(
            data=request.POST,
            instance=request.user.extended
        )
        user_tz = request.POST.get('timezone')
        if user_form.is_valid() and profile_form.is_valid():
            password = request.POST.get('old_password')
            if request.user.check_password(password):
                user = user_form.save(commit=False)
                new_pass = request.POST.get('new_password')
                do_redirect = False
                if len(new_pass):
                    print(new_pass)
                    user.set_password(new_pass)
                    do_redirect = True
                user.save()
                profile = profile_form.save(commit=False)
                profile.change_author = request.user
                profile.user = user
                if user_tz:
                    profile.timezone = user_tz
                profile.save()
                changed = True
                if do_redirect:
                    return HttpResponseRedirect(reverse('users:login'))
            else:
                raise ValidationError('Wrong password!')
        else:
            print(user_form.errors, profile_form.errors)
    else:
        user_form = EditUserForm(instance=request.user)
        profile_form = UserExtendedForm(instance=request.user.extended)

    return render(request, 'users/edit-profile.html',
                  {
                      'user_form': user_form,
                      'profile_form': profile_form,
                      'changed': changed,
                      'timezones': pytz.common_timezones,
                  })
