$(document).ready(function () {
    $('.ui.dropdown').dropdown();

    $('#save_notifications').click(function () {
        var notifications = [], self_ntf = false;
        $("input[id^='ntf__']").each(function () {
            var curr_id = $(this).attr('id').replace('ntf__', '');
            if ($(this).is(':checked')) {
                notifications.push(curr_id);
            }
        });
        if ($('#self_ntf').is(':checked')) {
            self_ntf = true;
        }
        $.post(
            '/users/ajax/save_notifications/',
            {self_ntf: self_ntf, notifications: JSON.stringify(notifications)},
            function (data) {
                data.status === 1 ? err_notify(data.message) : success_notify(data.message);
            },
            'json'
        );
    });

    $('.for_popup').popup();
    function check_sch_u_data() {
        var err_found = false, login = $('#scheduler_login'),
            password = $('#scheduler_password'),
            password_retype = $('#scheduler_password_retype'),
            confirm = $('#add_new_sch_u');
        if (login.val().length == 0) {
            err_found = true;
            $('#sch_u_login_warn').show();
            login.parent().addClass('error');
        }
        else {
            $('#sch_u_login_warn').hide();
            login.parent().removeClass('error');
        }
        if (password.val().length == 0) {
            err_found = true;
            $('#sch_u_password_warn').show();
            password.parent().addClass('error');
        }
        else {
            $('#sch_u_password_warn').hide();
            password.parent().removeClass('error');
        }
        if (password_retype.val().length == 0) {
            err_found = true;
            $('#sch_u_password_retype_warn').show();
            password_retype.parent().addClass('error');
        }
        else {
            $('#sch_u_password_retype_warn').hide();
            password_retype.parent().removeClass('error');
        }
        if (password.val().length > 0 && password_retype.val().length > 0 && password_retype.val() != password.val()) {
            err_found = true;
            $('#sch_u_password_retype_warn_2').show();
            password_retype.parent().addClass('error');
        }
        else {
            $('#sch_u_password_retype_warn_2').hide();
            password_retype.parent().removeClass('error');
        }
        if (err_found) {
            if (!confirm.hasClass('disabled')) {
                confirm.addClass('disabled');
            }
        }
        else {
            confirm.removeClass('disabled');
        }
        return err_found;
    }
    $('#scheduler_login').on('input', function () {
        check_sch_u_data();
    });
    $('#scheduler_password').on('input', function () {
        check_sch_u_data();
    });
    $('#scheduler_password_retype').on('input', function () {
        check_sch_u_data();
    });
    $('#add_new_sch_u').click(function () {
        $.ajax({
                url: '/service/ajax/add_scheduler_user/',
                data: {
                    login: $("#scheduler_login").val(),
                    password: $("#scheduler_password").val()
                },
                type: 'POST',
                success: function (data) {
                    if (data.error) {
                        err_notify(data.error);
                    }
                    else {
                        window.location.replace('');
                    }
                }
            });
    });
    $('#remove_sch_u_popup').modal({
        transition: 'fly up', autofocus: false, closable: false
    }).modal('attach events', '#remove_sch_u', 'show');
    $('#confirm_remove_sch_u').click(function () {
        $.ajax({
            url: '/service/ajax/remove_scheduler_user/',
            data: {},
            type: 'POST',
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    window.location.replace('');
                }
            }
        });
    });
    $('#cancel_remove_sch_u').click(function () {
        $('#remove_sch_u_popup').modal('hide');
    });
});