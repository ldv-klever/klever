/*
 * Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
 * Institute for System Programming of the Russian Academy of Sciences
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * ee the License for the specific language governing permissions and
 * limitations under the License.
 */

$(document).ready(function () {
    $('.ui.dropdown').dropdown();

    $('#process_job').click(function () {
        $.ajax({
            url: '/service/ajax/process_job/',
            data: {
                'job id': $('#job_selector').val()
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
            }
        });
    });

    $('#get_task_status_submit').click(function () {
        $.ajax({
            url: '/service/get_tasks_statuses/',
            data: {
                'tasks': JSON.stringify([$('#task_id').val()])
            },
            type: 'POST',
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    var statuses = JSON.parse(data['tasks statuses']);
                    if (statuses['pending'].length) {
                        success_notify("Task status: PENDING");
                    }
                    else if (statuses['processing'].length) {
                        success_notify("Task status: PROCESSING");
                    }
                    else if (statuses['finished'].length) {
                        success_notify("Task status: FINISHED");
                    }
                    else if (statuses['error'].length) {
                        success_notify("Task status: ERROR");
                    }
                }
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
            }
        });
    });

    $('#download_solution_submit').click(function () {
        var task_id = $('#task_id').val();
        if (task_id.length <= 0) {
            err_notify("Set task id");
            return false;
        }
        $.redirectPost('/service/download_solution/', {'task id': task_id});
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
                var get_jobs_and_tasks_res = $('#get_tasks_and_jobs_result');
                if (data.error) {
                    get_jobs_and_tasks_res.hide();
                    err_notify(data.error);
                }
                else {
                    get_jobs_and_tasks_res.text(data['jobs and tasks status']);
                    get_jobs_and_tasks_res.show();
                }
            }
        });
    });

    $('#download_task_submit').click(function () {
        var task_id = $('#download_task_task_id').val();
        if (task_id.length == 0) {
            err_notify("Set task id");
            return false;
        }
        $.redirectPost('/service/download_task/', {'task id': task_id});
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
            }
        });
    });
});