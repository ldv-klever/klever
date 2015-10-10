$(document).ready(function () {
    $('.ui.dropdown').dropdown();

    $('#add_new_scheduler_btn').click(function () {
         $.ajax({
            url: '/service/ajax/add_scheduler/',
            data: {
                'scheduler name': $('#new_scheduler_name').val(),
                'scheduler key': $('#new_scheduler_key').val(),
                'need auth': $('#new_scheduler_need_auth').val()
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
});