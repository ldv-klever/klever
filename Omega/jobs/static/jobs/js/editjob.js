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


function set_actions_for_edit_form () {
    check_all_roles();
    check_add_user_role();
    set_actions_for_file_form();

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
        var title_input = $('#job_title');
        var title = title_input.val(),
            comment = '',
            description = $('#job_description').val(),
            configuration = $('#job_config').val(),
            global_role = $('#job_global_roles').children('option:selected').val(),
            user_roles = [], job_id, job_id_input = $('#job_id_input');

        if (title.length == 0) {
            err_notify($('#title_required_div').html());
            title_input.focus();
            return false;
        }

        var job_coment = $('#job_comment');
        if (job_coment.length) {
            comment = job_coment.val();
            if (comment.length == 0) {
                err_notify($('#comment_required_div').html());
                job_coment.focus();
                return false;
            }
        }
        if (load_new_files()){
            console.log(111);
            var file_data = JSON.stringify(collect_filetable_data());
        }
        else {
            console.log(222);
            return false;
        }

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
                description: description,
                configuration: configuration,
                global_role: global_role,
                user_roles: user_roles,
                file_data: file_data,
                parent_identifier: $('#job_parent_identifier').val(),
                last_version: last_job_version
            },
            function (data) {
                data.status == 0 ? window.location.replace('/jobs/' + data.job_id + '/'):err_notify(data.message);
            },
            "json"
        );
    });

    $('#job_version_selector').change(function () {
        var version = $(this).children('option:selected').val();
        $.post(
            '/jobs/editjob/',
            {
                job_id: $("#job_id_input").val(),
                version: version
            },
            function (data) {
                $('#edit_job_div').html(data);
                set_actions_for_edit_form();
                $('#cancel_edit_job_btn').click(function () {
                    window.location.replace('');
                });
            }
        );
    });
}


function get_folders() {
    var options = [];
    $('input[id^="selected_filerow__0__"]').each(function () {
        var folder_id = $(this).attr('id').replace('selected_filerow__0__', '');
        var new_option = $('<option>', {
            value: folder_id,
            text: $('#file_title__0__' + folder_id).html()
        });
        options.push(new_option);
    });
    return options;
}


function load_new_files() {
    var file_inputs = $('#files_for_upload').children('input'),
        success = true;
    if (file_inputs.length > 0) {

        file_inputs.each(function () {
            console.log($(this).attr('id'));
            var current_input = $(this),
                data = new FormData(),
                curr_id = current_input.attr('id').replace('new_file_input__', '');
            data.append('file', current_input[0].files[0]);
            $.ajax({
                url: '/jobs/upload_files/',
                data: data,
                dataType: 'json',
                processData: false,
                type: 'POST',
                contentType: false,
                mimeType: 'multipart/form-data',
                async: false,
                success: function (data) {
                    if (data.status == 0) {
                        var file_hashsum = $('#file_hash_sum__1__' + curr_id);
                        console.log("ID:" + curr_id);
                        if (file_hashsum.length) {
                            file_hashsum.html(data.hash_sum);
                            current_input.remove();
                        }
                        else {
                            console.log(data);
                            success = false;
                        }
                    }
                    else {
                        var file_names = data.form_errors.file;
                        for (var i = 0; i < file_names.length; i++) {
                            err_notify(current_input.val() + ': ' + file_names[i], 10000);
                        }
                        success = false;
                    }
                }
            });
        });
    }
    $('#results').html('');
    return success;
}

function collect_filetable_data() {
    var data = [],
        success = true,
        re = /filerow__([01])__(\S*)/,
        re_parent = /treegrid-parent-(\S+)\s*/;
    $("tr[id^='filerow__']").each(function () {
        var m = $(this).attr('id').match(re);
        if (m) {
            var type = m[1],
                row_id = m[2],
                parent_id = null,
                hash_sum = null,
                title,
                object_title_span = $('#file_title__' + type + '__' + row_id);
            if (object_title_span.children('a').length > 0) {
                title = object_title_span.children('a').first().html();
            }
            else {
                title = object_title_span.html();
            }
            if (type == '1') {
                hash_sum = $('#file_hash_sum__' + type + '__' + row_id).html();
                if (hash_sum.length == 0) {
                    err_notify("One of the files was not uploaded!");
                    success = false;
                    return false;
                }
            }
            var parent_arr = $(this).attr('class').match(re_parent);
            if (parent_arr) {
                parent_id = parent_arr[1];
            }
            data.push({
                id: row_id,
                parent: parent_id,
                hash_sum: hash_sum,
                title: title,
                type: type
            });
        }
    });
    return data;
}

function new_filetable_row(type, id, parent_id, title, hash_sum, href) {
    var row_class = 'treegrid-' + id;
    if (parent_id) {
        row_class += ' treegrid-parent-' + parent_id;
    }
    if (type == 0) {
        row_class += ' success'
    }
    var new_row = $('<tr>', {
        id: 'filerow__' + type + '__' + id,
        class: row_class
    });
    new_row.append($('<td>', {class: 'col-sm-1'}).append($('<label>').append($('<input>', {
        id: 'selected_filerow__' + type + '__' + id,
        type: 'radio',
        name: 'selected_filerow',
        value: type + '__' + id
    }))));
    var title_span = $('<span>', {
        id: 'file_title__' + type + '__' + id,
        text: title
    });
    if (href) {
        title_span = $('<span>', {
            id: 'file_title__' + type + '__' + id
        }).append($('<a>', {
            href: href,
            text: title
        }));
    }
    var table_cell = $('<td>').append(title_span);
    if (type == 1) {
        table_cell.append($('<span>', {
            id: 'file_hash_sum__' + type + '__' + id,
            text: hash_sum,
            hidden: true
        }));
    }
    new_row.append(table_cell);
    return new_row;
}


function add_new_editform(template_id) {
    var editform = $('#edit_files_form');
    editform.html($('#' + template_id).html());
    editform.find("[id^='tmp___']").each(function () {
        var new_id = $(this).attr('id').replace('tmp___', '');
        $(this).attr('id', new_id);
    });
    editform.find("[for^='tmp___']").each(function () {
        var new_id = $(this).attr('for').replace('tmp___', '');
        $(this).attr('for', new_id);
    });
}


function update_treegrid() {
    $('.tree').treegrid({
        treeColumn: 1,
        expanderExpandedClass: 'treegrid-span-obj glyphicon glyphicon-folder-open',
        expanderCollapsedClass: 'treegrid-span-obj glyphicon glyphicon-folder-close'
    });
    $('input[id^="selected_filerow__"]').click(function () {
        $('#edit_files_form').html('');
    });
}

function selected_row() {
    var checked_radio = $('input[id^="selected_filerow__"]:checked');
    if (checked_radio.length > 0) {
        var full_id = checked_radio.attr('id').replace('selected_filerow__', '');
        return [full_id[0], full_id.replace(/^[01]__/, '')];
    }
    return null;
}

function set_actions_for_file_form() {
    update_treegrid();
    var cnt = 0;

    $('#new_folder_btn').click(function () {
        add_new_editform('new_folder_template');
        var parent_options = get_folders();
        for (var i = 0; i < parent_options.length; i++) {
            $('#new_folder_parent').append(parent_options[i]);
        }

        $('#create_new_folder_btn').click(function () {
            var fname = $('#new_folder_name').val();
            if (fname.length == 0) {
                err_notify("Folder name is required!");
            }
            else {
                var parent_id = $('#new_folder_parent').children('option:selected').val(),
                    parent_row = $('#filerow__0__' + parent_id);
                cnt++;
                if (parent_row.length) {
                    parent_row.after(
                        new_filetable_row(0, 'newdir_' + cnt, parent_id, fname)
                    );
                }
                else {
                    $('#file_tree_table').append(
                        new_filetable_row(0, 'newdir_' + cnt, null, fname)
                    );
                }
                update_treegrid();
                $('#edit_files_form').html('');
            }
        });

        $('#clear_file_form').click(function () {
            $('#edit_files_form').html('');
        });
    });


    $('#rename_file_btn').click(function () {
        var selected = selected_row();
        if (selected) {
            add_new_editform('rename_template');
            var title_span = $('#file_title__' + selected[0] + '__' + selected[1]);
            var old_title;
            if (title_span.children('a').length > 0) {
                old_title = title_span.children('a').first().html();
            }
            else {
                old_title = title_span.html();
            }
            $('#object_name').val(old_title);

            $('#change_name_btn').click(function () {
                var new_title = $('#object_name').val();
                if (new_title.length > 0) {
                    title_span.html(new_title);
                    $('#edit_files_form').html('');
                }
                else {
                    err_notify("Name is required!");
                }
            });

             $('#clear_file_form').click(function () {
                $('#edit_files_form').html('');
            });
        }
    });


    $('#move_file_btn').click(function () {
        var selected = selected_row();
        if (selected) {
            var sel_type = selected[0],
                sel_id = selected[1];
            if (sel_type != '1') {
                err_notify("Can't move folder.");
                return false;
            }
            add_new_editform('move_object_template');
            var file_title_span = $('#file_title__1__' + sel_id);
            var object_title, href = null;
            if (file_title_span.children('a').length > 0) {
                object_title = file_title_span.children('a').first().html();
                href = file_title_span.children('a').first().attr('href');
            }
            else {
                object_title = file_title_span.html();
            }
            var hash_sum = $('#file_hash_sum__1__' + sel_id).html();
            $('#moving_object_title').html(object_title);
            var new_opts = get_folders();
            for (var i = 0; i < new_opts.length; i++) {
                $('#move_object_parent').append(new_opts[i]);
            }

            $('#move_obj_btn').click(function () {
                var new_parent_id = $('#move_object_parent').children('option:selected').val(),
                    new_parent = $('#filerow__0__' + new_parent_id);
                $('#filerow__1__' + sel_id).remove();
                if (new_parent.length) {
                    new_parent.after(
                        new_filetable_row(1, sel_id, new_parent_id, object_title, hash_sum, href)
                    );
                }
                else {
                    $('#file_tree_table').append(
                        new_filetable_row(1, sel_id, null, object_title, hash_sum, href)
                    );
                }
                update_treegrid();
                $('#edit_files_form').html('');
            });

            $('#clear_file_form').click(function () {
                $('#edit_files_form').html('');
            });
        }
    });


    $('#remove_file_btn').click(function () {
        var selected = selected_row();
        if (selected) {
            var sel_type = selected[0],
                sel_id = selected[1];
            add_new_editform('remove_object_template');
            var object_title = $('#file_title__' + sel_type + '__' + sel_id).html();
            $('#remove_object_title').html(object_title);

            $('#remove_object_btn').click(function () {
                var objects_for_delete = [];
                var re_parent = /treegrid-parent-(\S+)\s*/;
                var children = [];
                children.push(sel_id);
                while (children.length > 0) {
                    $.merge(objects_for_delete, children);
                    children= [];
                    $('[id^="filerow__"]').each(function () {
                        var for_del = false,
                            parent_arr = $(this).attr('class').match(re_parent),
                            curr_id = $(this).attr('id').replace(/filerow__[01]__/, '');
                        if (parent_arr) {
                            var parent_id = parent_arr[1];
                            for (var i = 0; i < objects_for_delete.length; i++) {
                                if (objects_for_delete[i] == parent_id) {
                                    for_del = true;
                                }
                            }
                            if (for_del && objects_for_delete.indexOf(curr_id) == -1) {
                                children.push(curr_id);
                            }
                        }
                    });
                }
                for (var i = 0; i < objects_for_delete.length; i++) {
                    $("tr:regex(id,^filerow__[01]__" + objects_for_delete[i] + "$)").remove();
                    $('#new_file_input__' + objects_for_delete[i]).remove();
                }
                update_treegrid();
                $('#edit_files_form').html('');
            });

            $('#clear_file_form').click(function () {
                $('#edit_files_form').html('');
            });
        }
    });


    $('#new_file_btn').click(function () {
        add_new_editform('new_file_template');
        var new_opts = get_folders();
        for (var i = 0; i < new_opts.length; i++) {
            $('#new_file_parent').append(new_opts[i]);
        }

        $('.btn-file :file').on('fileselect', function (event, numFiles, label) {
            $('#new_file_name').val(label);
        });

        $('#save_new_file_btn').click(function () {
            var filename = $('#new_file_name').val(),
                parent_id = $('#new_file_parent').children('option:selected').val(),
                file_input = $('#new_file_input');

            if (file_input.val().length > 0) {
                if (filename.length > 0) {
                    var parent_row = $('#filerow__0__' + parent_id);
                    cnt++;
                    if (parent_row.length) {
                        parent_row.after(
                            new_filetable_row(1, 'newfile_' + cnt, parent_id, filename)
                        );
                    }
                    else {
                        $('#file_tree_table').append(
                            new_filetable_row(1, 'newfile_' + cnt, null, filename)
                        );
                    }
                    file_input.attr('id', 'new_file_input__newfile_' + cnt);
                    $('#files_for_upload').append(file_input);

                    update_treegrid();
                    $('#edit_files_form').html('');
                }
                else {
                    err_notify("File name is required!");
                }
            }
            else {
                err_notify("Choose the file!");
            }
        });

        $('#clear_file_form').click(function () {
            $('#edit_files_form').html('');
        });
    });

    return false;
}

$(document).ready(function () {
    if (!$('#resource_title_span').length) {
        $('#resource_star_div').hide();
    }

    if ($('#edit_job_div').length) {
        $.post(
            '/jobs/editjob/',
            {job_id: $('#job_pk').html()},
            function (data) {
                $('#edit_job_div').html(data);
                set_actions_for_edit_form();
                $('#cancel_edit_job_btn').click(function () {
                    window.location.replace('');
                });
            }
        ).fail(function (x) {
            console.log(x.responseText);
        });
    }
    else if($('#show_job_div').length) {
        $.ajax({
            url: '/jobs/showjobdata/',
            data: {job_id: $('#job_pk').html()},
            type: 'POST',
            success: function (data) {
                $('#show_job_div').html(data);
                $('.tree').treegrid({
                    treeColumn: 0,
                    expanderExpandedClass: 'treegrid-span-obj glyphicon glyphicon-folder-open',
                    expanderCollapsedClass: 'treegrid-span-obj glyphicon glyphicon-folder-close'
                });
            }
        });
    }
    else if($('#create_job_global_div').length) {
        set_actions_for_edit_form();
    }

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
                data.status == 0 ? window.location.replace('/jobs/'):err_notify(data.message);
            },
            'json'
        );
    });

    $('button[id^="load_job__"]').click(function () {
        var job_id = $(this).attr('id').replace('load_job__', '');
        var interval = null;
        var try_lock = function() {
            $.ajax({
                url: '/jobs/downloadlock/',
                type: 'GET',
                dataType: 'json',
                async: false,
                success: function (resp) {
                    if (resp.status) {
                        clearInterval(interval);
                        $('body').removeClass("loading");
                        window.location.replace('/jobs/downloadjob/' + job_id + '/' + '?hashsum=' + resp.hash_sum);
                    }
                },
                error: function(res) {
                    console.log(res.responseText);
                }
            });
        };
        $('body').addClass("loading");
        interval = setInterval(try_lock, 1000);
    });
});
