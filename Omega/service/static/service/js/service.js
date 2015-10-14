$(document).ready(function () {
    $('.ui.dropdown').dropdown();

    $('#add_new_scheduler_btn').click(function () {
        var for_jobs = $('#new_scheduler_for_jobs').is(":checked") ? "1" : "0";
        $.ajax({
            url: '/service/add_scheduler/',
            data: {
                'scheduler name': $('#new_scheduler_name').val(),
                'scheduler key': $('#new_scheduler_key').val(),
                'need auth': $('#new_scheduler_need_auth').val(),
                'for jobs': for_jobs
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

    $('#check_schedulers').click(function () {
        $.ajax({
            url: '/service/check_schedulers/',
            data: {
                'waiting time': $('#check_sch_time').val(),
                statuses: $('#check_sch_statuses').val()
            },
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

    $('#get_tasks_submit').click(function () {
        $.ajax({
            url: '/service/get_tasks/',
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
        $.ajax({
            url: '/service/init_session/',
            data: {
                'job id': $('#init_session_job_id').val(),
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
            },
            error: function (x) {
                console.log(x.responseText);
            }
        });
    });

    $('#close_session_submit').click(function () {
        $.ajax({
            url: '/service/close_session/',
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
            url: '/service/clear_sessions/',
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
            url: '/service/close_sessions/',
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

    $('#create_task_submit').click(function () {
        var data = new FormData();
        data.append('file', $('#create_task_archive')[0].files[0]);
        data.append('description', $('#create_task_description').val());
        data.append('session id', $('#create_task_session_id').val());
        data.append('priority', $('#create_task_priority').val());
        $.ajax({
            url: '/service/create_task/',
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

    $('#update_tools_submit').click(function () {
        $.ajax({
            url: '/service/update_tools/',
            data: {
                'scheduler key': $('#update_tools_schkey').val(),
                'tools data': $('#update_tools_data').val()
            },
            type: 'POST',
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    success_notify('Tools were updated');
                }
            },
            error: function (x) {
                console.log(x.responseText);
            }
        });
    });

    $('#get_task_status_submit').click(function () {
        $.ajax({
            url: '/service/get_task_status/',
            data: {
                'task id': $('#task_id').val()
            },
            type: 'POST',
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    success_notify("Task status: " + data['status']);
                }
            },
            error: function (x) {
                console.log(x.responseText);
            }
        });
    });

    $('#remove_task_submit').click(function () {
        $.ajax({
            url: '/service/remove_task/',
            data: {
                'task id': $('#task_id').val()
            },
            type: 'POST',
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    success_notify("Task was removed");
                }
            },
            error: function (x) {
                console.log(x.responseText);
            }
        });
    });

    $('#stop_task_submit').click(function () {
        $.ajax({
            url: '/service/stop_task/',
            data: {
                'task id': $('#task_id').val()
            },
            type: 'POST',
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    success_notify("Task was stopped");
                }
            },
            error: function (x) {
                console.log(x.responseText);
            }
        });
    });

    $('#get_task_solution_submit').click(function () {
        var task_id = $('#task_id').val();
        if (task_id.length <= 0) {
            err_notify("Set task id");
            return false;
        }
        window.open('/service/download_solution/' + task_id);
    });

    $('#get_task_submit').click(function () {
        var task_id = $('#download_task_task_id').val(),
            sch_key = encodeURIComponent($('#download_task_schkey').val());
        if (task_id.length <= 0) {
            err_notify("Set task id");
            return false;
        }
        if (sch_key.length <= 0) {
            err_notify("Set scheduler key");
            return false;
        }
        window.open('/service/download_task/' + task_id + "?key=" + sch_key);
    });

    $('#create_solution_submit').click(function () {
        var data = new FormData(), description = $('#create_solution_description').val();
        data.append('file', $('#create_solution_archive')[0].files[0]);
        if (description.length > 0) {
            data.append('description', description);
        }
        data.append('task id', $('#create_solution_task_id').val());
        data.append('scheduler key', $('#create_solution_schkey').val());
        $.ajax({
            url: '/service/create_solution/',
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
                else {
                    success_notify("Solution was successfully created");
                }
            },
            error: function (x) {
                console.log(x.responseText);
            }
        });
    });

    $('#update_nodes_submit').click(function () {
        $.ajax({
            url: '/service/update_nodes/',
            data: {
                'scheduler key': $('#update_nodes_schkey').val(),
                'nodes data': $('#update_nodes_data').val()
            },
            type: 'POST',
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    success_notify("Updated!");
                }
            },
            error: function (x) {
                console.log(x.responseText);
            }
        });
    });
});