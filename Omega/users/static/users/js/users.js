

$(document).ready(function () {
    var message_span = $('#profile_changed_span');
    if (message_span.length) {
        $.notify(message_span.html(), {
            autoHide: true,
            autoHideDelay: 2500,
            style: 'bootstrap',
            className: 'success'
        });
    }
});
