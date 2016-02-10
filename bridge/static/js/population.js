$(document).ready(function () {
    function check_usernames() {
        var manager_name = $('#manager_username'), service_name = $('#service_username');
        if (service_name.length && manager_name.length) {
            if (manager_name.val().length && manager_name.val() == service_name.val()) {
                $('#populate_button').addClass('disabled');
                $('#usernames_err').show();
            }
            else {
                $('#populate_button').removeClass('disabled');
                $('#usernames_err').hide();
            }
        }
    }
    $('#manager_username').on('input', function () {
        check_usernames();
    });
    $('#service_username').on('input', function () {
        check_usernames();
    });
});
