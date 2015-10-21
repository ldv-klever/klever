$(document).ready(function () {
    $('button[id^="rename_component_btn__"]').click(function () {
        $.post(
            '/service/ajax/change_component/',
            {
                action: 'rename',
                component_id: $(this).attr('id').replace('rename_component_btn__', ''),
                name: $('#component_name_input__' + $(this).attr('id').replace('rename_component_btn__', '')).val()
            },
            function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    success_notify(data.message);
                }
            }
        ).fail(function (x) {
                console.log(x.responseText);
            });
    });
    $('button[id^="delete_component_btn__"]').click(function () {
        $.post(
            '/service/ajax/change_component/',
            {
                action: 'delete',
                component_id: $(this).attr('id').replace('delete_component_btn__', '')
            },
            function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    success_notify(data.message);
                }
            }
        ).fail(function (x) {
                console.log(x.responseText);
            });
    });
    $('#clear_all_components').click(function () {
        $.post(
            '/service/ajax/clear_components_table/',
            {},
            function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    success_notify(data.message);
                }
            }
        ).fail(function (x) {
                console.log(x.responseText);
            });
    });
    $('#clear_all_problems').click(function () {
        $.post(
            '/service/ajax/clear_problems/',
            {},
            function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    success_notify(data.message);
                }
            }
        ).fail(function (x) {
                console.log(x.responseText);
            });
    });
    $('button[id^="delete_problem_btn__"]').click(function () {
        $.post(
            '/service/ajax/delete_problem/',
            {
                problem_id: $(this).attr('id').replace('delete_problem_btn__', '')
            },
            function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    success_notify(data.message);
                }
            }
        ).fail(function (x) {
                console.log(x.responseText);
            });
    });
});