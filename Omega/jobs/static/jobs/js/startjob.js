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
    $('#scheduler').dropdown({onChange: function () {
        var new_sch_u = $('#new_sch_u');
        if (new_sch_u.length) {
            if ($('#scheduler').val() == '1') {
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
        var data = {
            scheduler: $('#scheduler').val(),
            priority: $('#priority').val(),
            gen_priority: $('#gen_priority').val(),
            job_id: $('#job_pk').val(),
            cpu_model: $('#cpu_model').val()
        };
        var max_ram = $('#max_ram').val(),
            max_cpus = $('#max_cpus').val(),
            max_disk = $('#max_disk').val(),
            parallelism = $('#parallelism').val(),
            max_wall_time = $('#max_wall_time').val(),
            max_cpu_time = $('#max_cpu_time').val(),
            console_log_formatter = $('#console_log_formatter').val(),
            file_log_formatter = $('#file_log_formatter').val(),
            debug = false, allowlocaldir = false;
        if (!max_ram || !max_cpus || !max_disk || !parallelism || !console_log_formatter || !file_log_formatter || !max_wall_time || !max_cpu_time) {
            err_notify($('#fields_required').text());
        }
        else {
            data['max_ram'] = max_ram;
            data['max_wall_time'] = max_wall_time;
            data['max_cpu_time'] = max_cpu_time;
            data['max_cpus'] = max_cpus;
            data['max_disk'] = max_disk;
            data['parallelism'] = parallelism;
            data['console_log_formatter'] = console_log_formatter;
            data['file_log_formatter'] = file_log_formatter;
            if ($('#debug_checkbox').is(':checked')) {
                debug = true;
            }
            if ($('#allow_localdir_checkbox').is(':checked')) {
                allowlocaldir = true;
            }
            data['debug'] = debug;
            data['allow_local_dir'] = allowlocaldir;
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
                },
                error: function(x) {
                    console.log(x.responseText);
                }
            });
        }
    });
});
