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
    $('#autoupdate').parent().checkbox({onChange: function() {
        if ($('#autoupdate').is(':checked')) {
            interval = setInterval(update_table, 5000);
        }
        else {
            clearInterval(interval);
        }
    }});

    $('a[id^="show_tools_"]').click(function (event) {
        event.preventDefault();
        var tool_type = $(this).attr('id').replace('show_tools_', '');
        $('tr[class="active-tr"]').removeClass('active-tr');
        $('i[id^="tools_arrow_"]').hide();
        $('div[id^="tools_"]').hide();

        $(this).parent().parent().parent().addClass('active-tr');
        $('#tools_' + tool_type).show();
        $('#tools_arrow_' + tool_type).show();
    });
    $('.close-tools').click(function (event) {
        event.preventDefault();
        $('tr[class="active-tr"]').removeClass('active-tr');
        $('i[id^="tools_arrow_"]').hide();
        $('div[id^="tools_"]').hide();
    });

    $('a[id^="show_nodes_"]').click(function (event) {
        event.preventDefault();
        var conf_id = $(this).attr('id').replace('show_nodes_', '');
        $('[class^="node-of-conf-"]').removeClass('active-tr');
        $('.nodes-configuration').removeClass('active-tr');
        $('[id^="conf_info_"]').hide();
        $(this).parent().parent().parent().addClass('active-tr');
        $('.node-of-conf-' + conf_id).addClass('active-tr');
        $('#conf_info_' + conf_id).show();
    });
    $('.close-nodes-conf').click(function (event) {
        event.preventDefault();
        $('[class^="node-of-conf-"]').removeClass('active-tr');
        $('.nodes-configuration').removeClass('active-tr');
        $('[id^="conf_info_"]').hide();
    });
});