$(document).ready(function () {
    $('.ui.dropdown').dropdown();

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