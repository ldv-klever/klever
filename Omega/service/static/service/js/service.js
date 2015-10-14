$(document).ready(function () {
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
    $('.ui.checkbox').checkbox({onChange: function() {
        if ($('#autoupdate').is(':checked')) {
            interval = setInterval(update_table, 5000);
        }
        else {
            clearInterval(interval);
        }
    }});
});