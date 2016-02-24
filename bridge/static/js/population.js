$(document).ready(function () {
    var manager_input = $('#manager_username'), service_input = $('#service_username');
    function check_usernames() {
        if (service_input.length && manager_input.length) {
            if (manager_input.val().length == 0 || service_input.val().length == 0) {
                $('#populate_button').addClass('disabled');
                $('#usernames_required_err').show();
                return false;
            }
            else {
                $('#usernames_required_err').hide();
            }
            if (manager_input.val().length && manager_input.val() == service_input.val()) {
                $('#populate_button').addClass('disabled');
                $('#usernames_err').show();
            }
            else {
                $('#populate_button').removeClass('disabled');
                $('#usernames_err').hide();
            }
        }
    }
    manager_input.on('input', function () {
        check_usernames();
    });
    service_input.on('input', function () {
        check_usernames();
    });
    check_usernames();
});
