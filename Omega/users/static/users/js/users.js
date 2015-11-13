$(document).ready(function () {
    function get_scheduler_login_data() {
        var scheduler = $('#scheduler');
        $('#scheduler_login_data').hide();
        $('#remove_scheduler_login_data').hide();
        if (scheduler.children().length > 0) {
            $.ajax({
                url: '/service/ajax/get_scheduler_login_data/',
                data: {
                    'sch_id': scheduler.val()
                },
                type: 'POST',
                success: function (data) {
                    if (data.error) {
                        err_notify(data.error);
                    }
                    else if (data.login && data.password && data.max_priority) {
                        $('#scheduler_login_data').show();
                        $('#scheduler_login').text(data.login);
                        $('#new_scheduler_login').val(data.login);
                        $('#scheduler_password').text(data.password);
                        $('#new_scheduler_password').val(data.password);
                        $('#max_priority').text(data.max_priority);
                        $('#add_new_scheduler_data').text($('#update_scheduler_data_btn_text').text());
                        $('#remove_scheduler_login_data').show();
                    }
                    else {
                        $('#remove_scheduler_login_data').hide();
                        $('#add_new_scheduler_data').text($('#add_scheduler_data_btn_text').text());
                    }
                }
            });
        }
        else {
            $('#add_new_scheduler_data').hide();
        }
    }
    get_scheduler_login_data();
    $('#new_scheduler_data_popup').modal({transition: 'fly right', autofocus: false})
        .modal('attach events', '#add_new_scheduler_data', 'show');
    $('#add_scheduler_data_cancel').click(function () {
        $('#new_scheduler_data_popup').modal('hide');
    });
    $('.ui.dropdown').each(function () {
        if ($(this).attr('id') != 'scheduler') {
            $(this).dropdown()
        }
    });
    $('#remove_scheduler_login_data').click(function () {
        $.ajax({
            url: '/service/ajax/remove_sch_logindata/',
            data: {
                'sch_id': $('#scheduler').val()
            },
            type: 'POST',
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    $('#scheduler_login_data').hide();
                    $('#add_new_scheduler_data').text($('#add_scheduler_data_btn_text').text());
                    $('#remove_scheduler_login_data').hide();
                }
            }
        });
    });

    $('#add_scheduler_data_confirm').click(function() {
        var new_login = $('#new_scheduler_login'),
            new_password = $('#new_scheduler_password');
        if (new_login.val().length <= 0) {
            err_notify($('#new_login_scheduler_required').text());
            new_login.focus();
            return false;
        }
        else if (new_password.val().length <= 0) {
            err_notify($('#new_password_scheduler_required').text());
            new_password.focus();
            return false;
        }
        else {
            $('#new_scheduler_data_popup').modal('hide');
            $.ajax({
                url: '/service/ajax/add_scheduler_login_data/',
                data: {
                    sch_id: $('#scheduler').val(),
                    login: new_login.val(),
                    password: new_password.val(),
                    max_priority: $('#new_max_priority').val()
                },
                type: 'POST',
                success: function (data) {
                    if (data.error) {
                        err_notify(data.error);
                    }
                    else {
                        $('#scheduler_login_data').show();
                        $('#scheduler_login').text(new_login.val());
                        $('#scheduler_password').text(new_password.val());
                        $('#max_priority').text($('#new_max_priority').children(':selected').text());
                        $('#add_new_scheduler_data').text($('#update_scheduler_data_btn_text').text());
                        $('#remove_scheduler_login_data').show();
                    }
                }
            });
        }
    });

    $('#scheduler').dropdown({onChange: function () {
        get_scheduler_login_data();
    }});

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
});