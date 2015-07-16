function check_all_roles () {
    var global_role = $('#job_global_roles').children('option:selected').val();
    var gr_num = parseInt(global_role);
    if (gr_num == 4) {
        $('#job_user_role_div').hide();
        return false;
    }
    $('#all_user_roles').find("select[id^='job_user_role_select__']").each(function () {
        var is_dis = false;
        var has_selected = $(this).children('option[selected="selected"]').length;
        $(this).children('option').each(function () {
            var opt_num = parseInt($(this).val());
            if (opt_num < gr_num) {
                $(this).attr('disabled', 'disabled');
            }
            else if (opt_num == gr_num) {
                $(this).attr('disabled', 'disabled');
                is_dis = true;
            }
            else if (is_dis) {
                if (has_selected == 0) {
                    $(this).attr('selected', 'selected');
                }
                return false;
            }
        });
    });
    return false;
}

function check_add_user_role() {
    if ($('#job_available_users').children().length == 0) {
        $('#job_user_role_div').hide();
    }
    else {
        $('#job_user_role_div').show();
    }
}

function remove_user_role_form (id) {
    $('#job_available_users').append($('<option>', {
        value: id,
        text: $("label[for='job_user_role_select__" + id + "']").html()
    }));
    $('#job_user_role__' + id).remove();
}

function replace_or_notify(data, url) {
    if (data.status == 0) {
        window.location.replace(url)
    }
    else {
        $.notify(data.message, {
            autoHide: true,
            autoHideDelay: 2500,
            style: 'bootstrap',
            className: 'error'
        });
    }
}

function set_actions_for_edit_form () {
    check_all_roles();

    $('#add_user_for_role').click(function () {
        var selected_user = $('#job_available_users').children('option:selected');
        if (selected_user.length == 0) {
            return false;
        }
        var user_id = selected_user.val(), user_name = selected_user.html();
        var user_role_templ = $('#template__user_role').html();
        var new_user_role = $('<tr>', {
            id: ('job_user_role__' + user_id)
        });

        var tmp_tr = $('<tr>');
        tmp_tr.append(user_role_templ);
        tmp_tr.find("[for=job_user_role_select__]").each(function () {
            var old_id = $(this).attr('for');
            $(this).attr('for', old_id + user_id);
            $(this).html(user_name);
        });

        // new_user_role.append(user_role_templ);
        tmp_tr.find("[id]").each(function () {
            var old_id = $(this).attr('id');
            $(this).attr('id', old_id + user_id);
        });

        tmp_tr.children().each(function () {
            new_user_role.append($('<td>').append($(this)));
        });

        $('#all_user_roles').append(new_user_role);
        selected_user.remove();
        $("#remove_user_role__" + user_id).click(function () {
            $('#job_available_users').append($('<option>', {
                value: user_id,
                text: user_name
            }));
            $('#job_user_role__' + user_id).remove();
            check_add_user_role();
        });

        check_add_user_role();
        check_all_roles();
    });

    $("button[id^='remove_user_role__']").click(function () {
        var id = $(this).attr('id').replace('remove_user_role__', '');
        remove_user_role_form(id);
        check_add_user_role();
    });

    $('#job_global_roles').change(function() {
        $('#all_user_roles').find("tr[id^='job_user_role__']").each(function () {
            var id = $(this).attr('id').replace('job_user_role__', '');
            remove_user_role_form(id);
        });
        check_add_user_role();
        check_all_roles();
    });

    $('#save_job_btn').click(function () {
        var title = $('#job_title').val(),
            comment = $('#job_comment').val(),
            configuration = $('#job_config').val(),
            global_role = $('#job_global_roles').children('option:selected').val(),
            user_roles = [], job_id, job_id_input = $('#job_id_input');

        var last_job_version = 0;
        $('#job_version_selector').children('option').each(function () {
            var child_version = parseInt($(this).val());
            if (child_version > last_job_version) {
                last_job_version = child_version;
            }
        });

        if (job_id_input.length) {
            job_id = job_id_input.val();
        }
        $('#all_user_roles').find("select[id^='job_user_role_select__']").each(function () {
            var user_id = $(this).attr('id').replace('job_user_role_select__', ''),
                user_role = $(this).children('option:selected').val();
            user_roles.push({user: user_id, role: user_role});
        });
        user_roles = JSON.stringify(user_roles);
        $.post(
            '/jobs/savejob/',
            {
                job_id: job_id,
                title: title,
                comment: comment,
                configuration: configuration,
                global_role: global_role,
                user_roles: user_roles,
                parent_identifier: $('#job_parent_identifier').val(),
                last_version: last_job_version
            },
            function (data) {
                replace_or_notify(data, '/jobs/' + data.job_id + '/');
            },
            "json"
        );
    });

    $('#job_version_selector').change(function () {
        var version = $(this).children('option:selected').val();
        $.post(
            '/jobs/editjob/',
            {
                job_id: $("[id^='load_job__']").attr('id').replace('load_job__', ''),
                version: version
            },
            function (data) {
                var edit_job_div = $('#edit_job_div');
                edit_job_div.html(data);
                set_actions_for_edit_form();
                $('#cancel_edit_job_btn').click(function () {
                    $('#view_job_div').attr('class', 'col-sm-11');
                    edit_job_div.html('');
                    edit_job_div.attr('class', 'col-sm-1');
                });
            }
        );
    });
}

$(document).ready(function () {
    check_add_user_role();
    if (window.location.pathname == '/jobs/create/') {
        set_actions_for_edit_form();
    }

    $('button[id^="edit_job__"]').click(function () {
        var edit_job_div = $('#edit_job_div');
        $('#view_job_div').attr('class', 'col-sm-5');
        edit_job_div.attr('class', 'col-sm-7');
        $.post(
            '/jobs/editjob/',
            {job_id: $(this).attr('id').replace('edit_job__', '')},
            function (data) {
                $('#edit_job_div').html(data);
                set_actions_for_edit_form();
                $('#cancel_edit_job_btn').click(function () {
                    $('#view_job_div').attr('class', 'col-sm-11');
                    edit_job_div.html('');
                    edit_job_div.attr('class', 'col-sm-1');
                });
            }
        );
    });

    $("button[id^='copy_job__']").click(function () {
        var post_data = {
            parent_id: $(this).attr('id').replace('copy_job__', '')
        };
        $.redirectPost('/jobs/create/', post_data);
    });

    $('button[id^="remove_job__"]').click(function () {
        var job_id = $(this).attr('id').replace('remove_job__', '');
        $.post(
            '/jobs/removejob/',
            {job_id: job_id},
            function (data) {
                replace_or_notify(data, '/jobs/');
            },
            'json'
        );
    });
});