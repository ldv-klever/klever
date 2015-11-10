$(document).ready(function () {
    $('.ui.dropdown').dropdown();

    $('#process_job').click(function () {
        $.ajax({
            url: '/service/ajax/process_job/',
            data: {
                'job_id': $('#job_selector').val()
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

    $('#schedule_task_submit').click(function () {
        var data = new FormData();
        data.append('file', $('#schedule_task_archive')[0].files[0]);
        data.append('description', $('#schedule_task_description').val());
        $.ajax({
            url: '/service/schedule_task/',
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
                    success_notify("Task status: " + data['task status']);
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

    $('#download_solution_submit').click(function () {
        var task_id = $('#task_id').val();
        if (task_id.length <= 0) {
            err_notify("Set task id");
            return false;
        }
        window.open('/service/download_solution/' + task_id);
    });

    $('#cancel_task_submit').click(function () {
        $.ajax({
            url: '/service/cancel_task/',
            data: {
                'task id': $('#task_id').val()
            },
            type: 'POST',
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    success_notify("Task was cancelled");
                }
            },
            error: function (x) {
                console.log(x.responseText);
            }
        });
    });

    $('#add_sch_to_session').click(function () {
        $.ajax({
            url: '/service/ajax/fill_session/',
            data: {
                'scheduler': $('#sch_selector').val()
            },
            type: 'POST',
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    success_notify('Success');
                }
            }
        });
    });

    $('#get_tasks_and_jobs_submit').click(function () {
        $.ajax({
            url: '/service/get_jobs_and_tasks/',
            type: 'POST',
            data: {
                'jobs and tasks status': $('#get_tasks_and_jobs_json').val()
            },
            success: function (data) {
                if (data.error) {
                    $('#get_tasks_and_jobs_result').hide();
                    err_notify(data.error);
                }
                else {
                    $('#get_tasks_and_jobs_result').text(data['jobs and tasks status']);
                    $('#get_tasks_and_jobs_result').show();
                }
            },
            error: function (x) {
                $('#get_tasks_and_jobs_result').hide();
                console.log(x.responseText);
            }
        });
    });

    $('#download_task_submit').click(function () {
        var task_id = $('#download_task_task_id').val();
        if (task_id.length == 0) {
            err_notify("Set task id");
            return false;
        }
        window.open('/service/download_task/' + task_id);
    });

    $('#upload_solution_submit').click(function () {
        var data = new FormData(), description = $('#upload_solution_description').val();
        data.append('file', $('#upload_solution_archive')[0].files[0]);
        if (description.length > 0) {
            data.append('description', description);
        }
        data.append('task id', $('#upload_solution_task_id').val());
        $.ajax({
            url: '/service/upload_solution/',
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
                    success_notify("Solution was successfully uploaded");
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

    $('#update_tools_submit').click(function () {
        $.ajax({
            url: '/service/update_tools/',
            data: {
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

    $('#set_scheduler_status_confirm').click(function () {
        $.ajax({
            url: '/service/set_schedulers_status/',
            data: {
                statuses: $('#set_scheduler_status_statuses').val()
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
});