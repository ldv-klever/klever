$(document).ready(function () {
    var on_scheduler_click = function() {
        event.preventDefault();
        $.ajax({
            url: '/service/ajax/scheduler_job_sessions/',
            type: 'POST',
            data: {scheduler_id: $(this).next('span').text()},
            dataType: 'html',
            success: function (resp) {
                try {
                    JSON.parse(resp);
                    if (JSON.parse(resp) && JSON.parse(resp).error) {
                        err_notify(JSON.parse(resp).error);
                    }
                } catch (e) {
                    $('#scheduler_jobs_table').html(resp);
                }
            },
            error: function(x) {
                console.log(x.responseText);
            }
        });
    };
    var interval;
    var update_table = function() {
        $.ajax({
            url: '/service/ajax/update_jobs/' + $('#user_id').val(),
            type: 'GET',
            dataType: 'html',
            success: function (resp) {
                try {
                    JSON.parse(resp);
                    if (JSON.parse(resp) && JSON.parse(resp).error) {
                        clearInterval(interval);
                        err_notify(JSON.parse(resp).error);
                        $('#autoupdate').prop('checked', false);
                    }
                } catch (e) {
                    $('#jobs_table').html(resp);
                }
            }
        });
    };
    $('#autoupdate').parent().checkbox({onChange: function() {
        if ($('#autoupdate').is(':checked')) {
            interval = setInterval(update_table, 5000);
        }
        else {
            clearInterval(interval);
        }
    }});

    $('.get-schedulers-table').click(function (event) {
        event.preventDefault();
        $('#scheduler_jobs_table').empty();
        $.ajax({
            url: '/service/ajax/scheduler_sessions/',
            type: 'POST',
            data: {session_id: $(this).parent().find('span').text()},
            dataType: 'html',
            success: function (resp) {
                try {
                    JSON.parse(resp);
                    if (JSON.parse(resp) && JSON.parse(resp).error) {
                        err_notify(JSON.parse(resp).error);
                    }
                } catch (e) {
                    $('#schedulers_table').html(resp);
                    $('.get-jobs-table').click(on_scheduler_click);
                }
            },
            error: function(x) {
                console.log(x.responseText);
            }
        });
    });
});