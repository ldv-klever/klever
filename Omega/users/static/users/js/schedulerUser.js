$(document).ready(function () {
    $('.for_popup').popup();
    function check_sch_u_data() {
        var err_found = false, login = $('#scheduler_login'),
            password = $('#scheduler_password'),
            password_retype = $('#scheduler_password_retype'),
            confirm = $('#submit_settings');
        if (login.val().length == 0 && $('#sch_user_delete_warn').length) {
            $('#sch_user_delete_warn').show();
        }
        else {
            $('#sch_user_delete_warn').hide();
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
});
