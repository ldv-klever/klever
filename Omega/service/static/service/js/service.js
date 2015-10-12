$(document).ready(function () {
    $('.ui.dropdown').dropdown();

    $('#add_new_scheduler_btn').click(function () {
         $.ajax({
            url: '/service/ajax/add_scheduler/',
            data: {
                'scheduler name': $('#new_scheduler_name').val(),
                'scheduler key': $('#new_scheduler_key').val(),
                'need auth': $('#new_scheduler_need_auth').val()
            },
            type: 'POST',
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    success_notify('Scheduler added successfully');
                }
            }
        });
    });

    $('#get_tasks_submit').click(function () {
        $.ajax({
            url: '/service/ajax/get_tasks/',
            type: 'POST',
            data: {
                'scheduler key': $('#get_tasks_sch_key').val(),
                'tasks list': $('#get_tasks_json_tasks').val()
            },
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    $('#get_tasks_result').text(data['tasks list']);
                }
            },
            error: function (x) {
                console.log(x.responseText);
            }
        });
    });

    $('#init_session_submit').click(function () {
        var schedulers = $('#init_session_sch_names').val().split(',');
        $.ajax({
            url: '/service/ajax/init_session/',
            data: {
                'job id': $('#init_session_job_id').val(),
                schedulers: JSON.stringify(schedulers),
                'max priority': $('#init_session_priority').val(),
                'verifier name': $('#init_session_tool_name').val(),
                'verifier version': $('#init_session_tool_version').val()
            },
            type: 'POST',
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else if (data['session id']) {
                    success_notify('Session was initialised! ID: ' + data['session id']);
                }
                else {
                    err_notify('jQuery failed!');
                }
            }
        });
    });

    $('#close_session_submit').click(function () {
        $.ajax({
            url: '/service/ajax/close_session/',
            data: {
                'session id': $('#close_session_session_id').val()
            },
            type: 'POST',
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    success_notify('Session was successfully closed');
                }
            },
            error: function (x) {
                console.log(x.responseText);
            }
        });
    });

    $('#clear_sessions_submit').click(function () {
        $.ajax({
            url: '/service/ajax/clear_sessions/',
            data: {
                hours: $('#clear_sessions_hours').val()
            },
            type: 'POST',
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    success_notify('Sessions were successfully cleared');
                }
            },
            error: function (x) {
                console.log(x.responseText);
            }
        });
    });

    $('#close_sessions_submit').click(function () {
        $.ajax({
            url: '/service/ajax/close_sessions/',
            data: {
                minutes: $('#close_sessions_minutes').val()
            },
            type: 'POST',
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    success_notify('Sessions were successfully closed');
                }
            },
            error: function (x) {
                console.log(x.responseText);
            }
        });
    });

    $('#check_schedulers').click(function () {
        $.ajax({
            url: '/service/ajax/check_schedulers/',
            data: {},
            type: 'POST',
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    success_notify('Success!');
                }
            },
            error: function (x) {
                console.log(x.responseText);
            }
        });
    });

    $('#create_task_submit').click(function () {
        var data = new FormData();
        data.append('file', $('#create_task_description')[0].files[0]);
        data.append('file', $('#create_task_archive')[0].files[0]);
        data.append('session id', $('#create_task_session_id').val());
        data.append('priority', $('#create_task_priority').val());
        $.ajax({
            url: '/service/ajax/create_task/',
            type: 'POST',
            data: data,
            processData: false,
            contentType: false,
            dataType: 'json',
            mimeType: 'multipart/form-data',
            async: false,
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else if (data['task id']) {
                    success_notify("Task was created. ID: " + data['task id']);
                }
                else {
                    console.log(data);
                }
            },
            error: function (x) {
                console.log(x.responseText);
            }
        });
    });
});