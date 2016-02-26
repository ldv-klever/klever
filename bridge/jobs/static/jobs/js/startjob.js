function set_actions_for_scheduler_user() {
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
                    success_notify($('#sch_u_saved').text(), 10000);
                    $('#new_sch_u').remove();
                    $('.need-auth').show();
                }
            }
        });
    });
}


$(document).ready(function () {
    $('.normal-dropdown').dropdown();
    $('.ui.scheduler-checkbox').addClass('checkbox');
    $('.scheduler-checkbox').checkbox({onChecked: function () {
        var new_sch_u = $('#new_sch_u');
        if (new_sch_u.length) {
            if ($(this).val() == '1') {
                new_sch_u.show();
                $('.need-auth').hide();
            }
            else {
                new_sch_u.hide();
                $('.need-auth').show();
            }
        }
    }});
    set_actions_for_scheduler_user();
    $('#start_job_decision').click(function () {
        var required_fields = [
            'max_ram', 'max_cpus', 'max_disk',
            'parallelism_linux_kernel_build', 'parallelism_tasks_generation',
            'console_log_formatter', 'file_log_formatter'
        ], err_found = false;
        $.each(required_fields, function (i, v) {
            var curr_input = $('#' + v);
            curr_input.parent().removeClass('error');
            if (!curr_input.val()) {
                curr_input.parent().addClass('error');
                err_found = true;
            }
        });
        if (err_found) {
            err_notify($('#fields_required').text());
        }
        else {
            var data = {
                scheduler: $('input[name="scheduler"]:checked').val(),
                priority: $('input[name="priority"]:checked').val(),
                avtg_priority: $('input[name="avtg_priority"]:checked').val(),
                job_id: $('#job_pk').val(),
                cpu_model: $('#cpu_model').val(),
                max_wall_time: $('#max_wall_time').val(),
                max_cpu_time: $('#max_cpu_time').val(),
                debug: $('#debug_checkbox').is(':checked'),
                allow_local_dir: $('#allow_localdir_checkbox').is(':checked')
            };
            $.each(required_fields, function (i, v) {
                data[v] = $('#' + v).val();
            });
            $.ajax({
                url: job_ajax_url + 'run_decision/',
                data: {data: JSON.stringify(data)},
                type: 'POST',
                success: function (data) {
                    if (data.error) {
                        err_notify(data.error);
                    }
                    else {
                        window.location.replace($('#job_link').attr('href'));
                    }
                }
            });
        }
    });
});
