/*
 * Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
 * Institute for System Programming of the Russian Academy of Sciences
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * ee the License for the specific language governing permissions and
 * limitations under the License.
 */

var readable_extensions = ['txt', 'json', 'xml', 'c', 'aspect', 'i', 'h', 'tmpl'];

function isFileReadable(name) {
    var found = name.lastIndexOf('.') + 1,
        extension = (found > 0 ? name.substr(found) : "");
    return ($.inArray(extension, readable_extensions) !== -1);
}


function check_filename(str) {
    if (str.length > 0) {
        if (isASCII(str) || str.length < 30) {
            return true;
        }
        else {
            err_notify($("#error__filename_not_ascii").text());
            return false;
        }
    }
    err_notify($('#error__name_required').text());
    return false;
}


function set_actions_for_edit_form () {

    function check_all_roles() {
        var global_role = $('#job_global_roles').children('option:selected').val();
        var gr_num = parseInt(global_role);
        if (gr_num === 4) {
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
                else if (opt_num === gr_num) {
                    $(this).attr('disabled', 'disabled');
                    is_dis = true;
                }
                else if (is_dis) {
                    if (has_selected === 0) {
                        $(this).attr('selected', 'selected');
                    }
                    return false;
                }
            });
        });
        return false;
    }

    function remove_user_role_form (id) {
        $('#job_available_users').append($('<option>', {
            value: id,
            text: $("label[for='job_user_role_select__" + id + "']").text()
        }));
        $('#job_user_role__' + id).remove();
    }

    function check_add_user_role() {
        if ($('#job_available_users').children().length === 0) {
            $('#job_user_role_div').hide();
        }
        else {
            $('#job_user_role_div').show();
        }
    }

    check_add_user_role();
    check_all_roles();
    set_actions_for_file_form();
    $('.ui.dropdown').dropdown();

    $('.files-actions-popup').popup({position: 'bottom right'});

    $('#add_user_for_role').click(function () {
        var user_selector = $('#job_available_users'),
            selected_user = user_selector.children('option:selected');
        if (selected_user.length === 0) {
            return false;
        }
        var user_id = selected_user.val(), user_name = selected_user.text();
        var user_role_templ = $('#template__user_role').html();
        var new_user_role = $('<div>', {
            id: ('job_user_role__' + user_id),
            class: 'ui grid segment'
        });

        var tmp_div = $('<div>');
        tmp_div.append(user_role_templ);
        tmp_div.find("[for=job_user_role_select__]").each(function () {
            var old_id = $(this).attr('for');
            $(this).attr('for', old_id + user_id);
            $(this).text(user_name);
        });

        tmp_div.find("[id]").each(function () {
            var old_id = $(this).attr('id');
            $(this).attr('id', old_id + user_id);
        });
        tmp_div.find("select[id^='job_user_role_select__']").attr('class', 'ui dropdown');

        $('#all_user_roles').append(new_user_role.append(tmp_div.html()));
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
        user_selector.dropdown('set selected', user_selector.children().first().val()).dropdown('refresh');
        $('.ui.dropdown').each(function () {
            if ($(this).find('select').first().attr('id') != user_selector.attr('id')) {
                $(this).dropdown();
            }
        });
    });

    $("button[id^='remove_user_role__']").click(function () {
        var id = $(this).attr('id').replace('remove_user_role__', '');
        remove_user_role_form(id);
        check_add_user_role();
    });

    $('#job_global_roles').change(function() {
        $('#all_user_roles').find("div[id^='job_user_role__']").each(function () {
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
            global_role = $('#job_global_roles').children('option:selected').val(),
            user_roles = [], job_id, job_pk = $('#job_pk');

        if (title.length === 0) {
            err_notify($('#error__title_required').text());
            title_input.focus();
            return false;
        }

        var tmp_div = $('<div>').html(description);
        tmp_div.find('script').remove();
        tmp_div.find('*').each(function () {
            var element_in_div = $(this);
            $.each($(this)[0].attributes, function (i, attr) {
                if (attr.name.match("^on")) {
                    element_in_div.removeAttr(attr.name)
                }
            });
        });
        description = tmp_div.html();

        var job_coment = $('#job_comment');
        if (job_coment.length) {
            comment = job_coment.val();
            if (comment.length === 0) {
                err_notify($('#error__comment_required').text());
                job_coment.focus();
                return false;
            }
        }
        if (!load_new_files()) {
            return false;
        }
        var file_data = JSON.stringify(collect_filetable_data()),
            last_job_version = 0;
        $('#job_version_selector').children('option').each(function () {
            var child_version = parseInt($(this).val());
            if (child_version > last_job_version) {
                last_job_version = child_version;
            }
        });

        if (job_pk.length) {
            job_id = job_pk.val();
        }
        $('#all_user_roles').find("select[id^='job_user_role_select__']").each(function () {
            var user_id = $(this).attr('id').replace('job_user_role_select__', ''),
                user_role = $(this).children('option:selected').val();
            user_roles.push({user: user_id, role: user_role});
        });
        user_roles = JSON.stringify(user_roles);
        $('#dimmer_of_page').addClass('active');
        $.post(
            job_ajax_url + 'savejob/',
            {
                job_id: job_id,
                title: title,
                comment: comment,
                description: description,
                global_role: global_role,
                user_roles: user_roles,
                file_data: file_data,
                parent_identifier: $('#job_parent_identifier').val(),
                last_version: last_job_version,
                safe_marks: $('#safe_marks_checkbox').is(':checked')
            },
            function (data) {
                $('#dimmer_of_page').removeClass('active');
                data.error ? err_notify(data.error) : window.location.replace('/jobs/' + data.job_id + '/');
            },
            "json"
        );
    });

    $('#job_version_selector').change(function () {
        var version = $(this).children('option:selected').val();
        $.post(
            job_ajax_url + 'editjob/',
            {
                job_id: $("#job_pk").val(),
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


function load_new_files() {
    var file_inputs = $('#files_for_upload').children('input'),
        success = true;
    if (file_inputs.length > 0) {
        file_inputs.each(function () {
            var current_input = $(this),
                data = new FormData(),
                curr_id = current_input.attr('id').replace('new_file_input__', '');
            data.append('file', current_input[0].files[0]);
            $.ajax({
                url: job_ajax_url + 'upload_file/',
                data: data,
                dataType: 'json',
                processData: false,
                type: 'POST',
                contentType: false,
                mimeType: 'multipart/form-data',
                async: false,
                success: function (data) {
                    if (data.error) {
                        err_notify(data.error);
                        success = false;
                    }
                    else {
                        var file_hashsum = $('#file_hash_sum__1__' + curr_id);
                        if (file_hashsum.length) {
                            file_hashsum.text(data['checksum']);
                            current_input.remove();
                        }
                        else {
                            success = false;
                        }
                    }
                }
            });
        });
    }
    $('#results').empty();
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
                title = object_title_span.children('a').first().text();
            }
            else {
                title = object_title_span.text();
            }
            if (type === '1') {
                hash_sum = $('#file_hash_sum__' + type + '__' + row_id).text();
                if (hash_sum.length === 0) {
                    err_notify($('#error__file_not_uploaded').text());
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
    var new_row = $('<tr>', {
        id: 'filerow__' + type + '__' + id,
        class: row_class
    });
    if (type === 0) {
        new_row.attr('style', 'background:#eee8b7;')
    }
    new_row.append($('<td>', {class: 'one wide right aligned'}).append($('<div>', {class: 'ui radio checkbox'}).append($('<input>', {
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
    if (type === 1) {
        table_cell.append($('<span>', {
            id: 'file_hash_sum__' + type + '__' + id,
            text: hash_sum,
            hidden: true
        }));
    }
    new_row.append(table_cell);
    return new_row;
}


function update_treegrid() {
    inittree($('.tree'), 2, 'folder open violet icon', 'folder violet icon');
}

function selected_row() {
    var checked_radio = $('input[id^="selected_filerow__"]:checked');
    if (checked_radio.length > 0) {
        var full_id = checked_radio.attr('id').replace('selected_filerow__', '');
        return [full_id[0], full_id.replace(/^[01]__/, '')];
    }
    return null;
}

function set_action_on_file_click () {
    $('#file_tree_table').find('a').click(function (event) {
        var href = $(this).attr('href'), file_name = $(this).text(),
            close_fileview_btn = $('#close_file_view'),
            download_file_btn = $('#download_file_form_view');
        $('#file_content_modal').modal('setting', 'transition', 'fade');
        if (isFileReadable(file_name)) {
            event.preventDefault();
            $.ajax({
                url: job_ajax_url + 'getfilecontent/',
                data: {file_id: $(this).parent().attr('id').split('__').pop()},
                type: 'POST',
                success: function (data) {
                    try {
                        JSON.stringify(data);
                        JSON.stringify(data);
                        err_notify(data.message);
                    } catch (e) {
                        close_fileview_btn.unbind();
                        close_fileview_btn.click(function () {
                            $('#file_content_modal').modal('hide');
                            $('#file_content').empty();
                        });
                        download_file_btn.unbind();
                        download_file_btn.click(function () {
                            $('#file_content_modal').modal('hide');
                            window.location.replace(href);
                        });
                        $('#file_content_name').text(file_name);
                        $('#file_content').text(data);
                        $('#file_content_modal').modal('show');
                    }
                }
            });
        }
    });
}

function set_actions_for_file_form() {

    function get_folders() {
        var options = [];
        $('input[id^="selected_filerow__0__"]').each(function () {
            var folder_id = $(this).attr('id').replace('selected_filerow__0__', '');
            var new_option = $('<option>', {
                value: folder_id,
                text: $('#file_title__0__' + folder_id).text()
            });
            options.push(new_option);
        });
        return options;
    }

    update_treegrid();
    set_action_on_file_click();
    $('.ui.checkbox').checkbox();
    var cnt = 0;

    $('#new_folder_modal').modal({onShow: function () {
        var folder_parents = $('#new_folder_parent'),
            confirm_btn = $('#create_new_folder_btn');
        folder_parents.children('option[value!="root"]').remove();
        $('#new_folder_name').val('');
        var parent_options = get_folders();
        for (var i = 0; i < parent_options.length; i++) {
            folder_parents.append(parent_options[i]);
        }
        folder_parents.dropdown('set selected', folder_parents.children().first().val());

        confirm_btn.unbind('click');
        confirm_btn.click(function () {
            var fname = $('#new_folder_name').val();
            if (check_filename(fname)) {
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
                $('.ui.checkbox').checkbox();
                $('#new_folder_modal').modal('hide');
            }
        });
    }, transition: 'fly left'}).modal('attach events', '#new_folder_btn', 'show');


    $('#new_file_modal').modal({onShow: function () {
        var new_opts = get_folders(), file_parents = $('#new_file_parent'),
            file_input = $('#new_file_input'), confirm_btn = $('#save_new_file_btn');
        file_parents.children('option[value!="root"]').remove();
        $('#new_file_name').val('');
        file_input.replaceWith(file_input.clone(true));
        for (var i = 0; i < new_opts.length; i++) {
            file_parents.append(new_opts[i]);
        }
        file_parents.dropdown('set selected', file_parents.children().first().val());

        $('.btn-file :file').on('fileselect', function (event, numFiles, label) {
            $('#new_file_name').val(label);
        });
        confirm_btn.unbind('click');
        confirm_btn.click(function () {
            var filename = $('#new_file_name').val(),
                parent_id = $('#new_file_parent').children('option:selected').val(),
                file_input = $('#new_file_input');

            if (file_input.val().length > 0) {
                if (check_filename(filename)) {
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
                    $('#new_file_input_btn').append($('<input>', {
                        id: 'new_file_input',
                        type: 'file'
                    }));

                    update_treegrid();
                    $('.ui.checkbox').checkbox();
                    $('#new_file_modal').modal('hide');
                }
            }
            else {
                err_notify($('#error__nofile_selected').text());
            }
        });
    }, transition: 'fly left'}).modal('attach events', '#new_file_btn', 'show');

    $('#rename_modal').modal({transition: 'fly left'});
    $('#rename_file_btn').click(function () {
        var selected = selected_row();
        if (selected) {
            $('#rename_modal').modal('show');
            var title_span = $('#file_title__' + selected[0] + '__' + selected[1]),
                confirm_btn = $('#change_name_btn'), old_title;
            if (title_span.children('a').length > 0) {
                old_title = title_span.children('a').first().text();
            }
            else {
                old_title = title_span.text();
            }
            $('#object_name').val(old_title);

            confirm_btn.unbind('click');
            confirm_btn.click(function () {
                var new_title = $('#object_name').val();
                if (old_title != new_title && check_filename(new_title)) {
                    title_span.text(new_title);
                }
                $('#rename_modal').modal('hide');
            });
        }
        else {
            err_notify($('#error__noobj_to_rename').text());
        }
    });

    $('#move_file_modal').modal({transition: 'fly left'});
    $('#move_file_btn').click(function () {
        var selected = selected_row();
        if (selected) {
            var sel_type = selected[0],
                sel_id = selected[1];
            if (sel_type != '1') {
                err_notify($('#error__cant_move_dir').text());
                return;
            }
            $('#move_file_modal').modal('show');
            var file_title_span = $('#file_title__1__' + sel_id);
            var object_title, href = null;
            if (file_title_span.children('a').length > 0) {
                object_title = file_title_span.children('a').first().text();
                href = file_title_span.children('a').first().attr('href');
            }
            else {
                object_title = file_title_span.text();
            }
            var hash_sum = $('#file_hash_sum__1__' + sel_id).text(),
                file_parents = $('#move_object_parent'), confirm_btn = $('#move_obj_btn');
            $('#moving_object_title').text(object_title);
            file_parents.children('option[value!="root"]').remove();
            var new_opts = get_folders();
            for (var i = 0; i < new_opts.length; i++) {
                file_parents.append(new_opts[i]);
            }
            file_parents.dropdown('set selected', file_parents.children().first().val());

            confirm_btn.unbind('click');
            confirm_btn.click(function () {
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
                set_action_on_file_click();
                $('.ui.checkbox').checkbox();
                $('#move_file_modal').modal('hide');
            });
        }
        else {
            err_notify($('#error__cant_move_file').text());
        }
    });

    $('#remove_object_modal').modal({transition: 'fly left'});
    $('#remove_obj_btn').click(function () {
        var selected = selected_row();
        if (selected) {
            $('#remove_object_modal').modal('show');
            var sel_type = selected[0], sel_id = selected[1],
                object_title = $('#file_title__' + sel_type + '__' + sel_id).text(),
                confirm_btn = $('#remove_object_btn');
            $('#remove_object_title').text(object_title);

            confirm_btn.unbind('click');
            confirm_btn.click(function () {
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
                                if (objects_for_delete[i] === parent_id) {
                                    for_del = true;
                                }
                            }
                            if (for_del && objects_for_delete.indexOf(curr_id) === -1) {
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
                $('#remove_object_modal').modal('hide');
            });
        }
        else {
            err_notify($('#error__noobj_to_delete').text());
        }
    });

    $('#replace_file_modal').modal({transition: 'fly left'});
    $('#replace_file_btn').click(function () {
        var selected = selected_row();
        if (selected) {
            var sel_type = selected[0],
                sel_id = selected[1],
                files_table = $('#file_tree_table'),
                file_title_span = $('#file_title__1__' + sel_id);
            if (sel_type != 1) {
                err_notify($('#error__cant_replace_folder').text());
                return;
            }
            if (file_title_span.children('a').length > 0) {
                $('#replaced_file_name').text(file_title_span.children('a').first().text());
            }
            else {
                $('#replaced_file_name').text(file_title_span.text());
            }

            var file_input = $('#replace_file_input');
            $('#replace_file_name').val('');
            file_input.replaceWith(file_input.clone(true));

            $('#replace_file_modal').modal('show');

            $('.btn-file :file').on('fileselect', function (event, numFiles, label) {
                $('#replace_file_name').val(label);
            });
            var confirm_btn = $('#replace_file_confirm');
            confirm_btn.unbind('click');
            confirm_btn.click(function () {
                var filename = $('#replace_file_name').val(),
                    file_input = $('#replace_file_input');

                if (file_input.val().length > 0) {
                    if (check_filename(filename)) {
                        cnt++;
                        file_input.attr('id', 'new_file_input__newfile_' + cnt);
                        $('#files_for_upload').append(file_input);
                        $('#replace_file_input_btn').append($('<input>', {
                            id: 'replace_file_input',
                            type: 'file'
                        }));

                        $('#file_title__1__' + sel_id).text(filename);
                        $('#file_hash_sum__1__' + sel_id).empty();
                        $('#new_file_input__' + sel_id).remove();

                        files_table.find("[id$='__1__" + sel_id + "']").each(function () {
                            var id_start = $(this).attr('id').replace('__1__' + sel_id, '');
                            $(this).attr('id', id_start + '__1__' + 'newfile_' + cnt);
                        });
                        files_table.find("tr[class='treegrid-" + sel_id + "']").each(function () {
                            $(this).attr('class', 'treegrid-newfile_' + cnt);
                        });
                        update_treegrid();
                        $('#replace_file_modal').modal('hide');
                    }
                }
                else {
                    err_notify($('#error__nofile_selected').text());
                }
            });
        }
        else {
            err_notify($('#error__noselected_replace').text());
        }
    });
    $('.clear-modal').click(function () {
        $('.ui.modal').modal('hide');
    });

    return false;
}


function set_actions_for_versions_delete() {
    $('.ui.checkbox').checkbox();

    $('#remove_versions_popup').modal({transition: 'fly up', autofocus: false, closable: false})
        .modal('attach events', '#show_remove_versions_modal', 'show');
    $('#cancel_edit_job_btn').click(function () {
        window.location.replace('');
    });
    $('#reload_page__versions').click(function () {
        window.location.replace('');
    });
    $('#cancel_remove_versions').click(function () {
        $('#remove_versions_popup').modal('hide');
    });

    $('#delete_versions_btn').click(function () {
        $('#remove_versions_popup').modal('hide');
        var checked_versions = [];
        $('input[id^="checkbox_version__"]').each(function () {
            if ($(this).is(':checked')) {
                checked_versions.push($(this).attr('id').replace('checkbox_version__', ''));
            }
        });
        $.post(
            job_ajax_url + 'remove_versions/',
            {job_id: $('#job_pk').val(), versions: JSON.stringify(checked_versions)},
            function (data) {
                data.error ? err_notify(data.error) : success_notify(data.message);
                var global_parent = $('#versions_rows');
                $.each(checked_versions, function (i, val) {
                    var version_line = $("#checkbox_version__" + val).closest('.version-line');
                    if (version_line.length) {
                        version_line.remove();
                    }

                });
                if (global_parent && global_parent.children().first().children().length == 0) {
                    $('#versions_to_delete').hide();
                    $('#no_versions_to_delete').show();
                }
            },
            'json'
        );
    });
}
function activate_download_for_compet() {
    var dfc_modal = $('#dfc_modal');
    $('#dfc_modal_show').popup();
    dfc_modal.modal({transition: 'slide down', autofocus: false, closable: false}).modal('attach events', '#dfc_modal_show', 'show');
    dfc_modal.find('.ui.checkbox').checkbox();
    $('#dfc__f').parent().checkbox({
        onChecked: function () {
            $('#dfc_problems').show();
        },
        onUnchecked: function () {
            $('#dfc_problems').hide();
        }
    });
    $('#dfc__cancel').click(function () {
        $('#dfc_modal').modal('hide');
    });
    $('#dfc__confirm').click(function () {
        var svcomp_filters = [];
        if ($('#dfc__u').parent().checkbox('is checked')) {
            svcomp_filters.push('u');
        }
        if ($('#dfc__s').parent().checkbox('is checked')) {
            svcomp_filters.push('s');
        }
        if ($('#dfc__f').parent().checkbox('is checked')) {
            var unknowns_filters = [];
            $('input[id^="dfc__p__"]').each(function () {
                if ($(this).parent().checkbox('is checked')) {
                    unknowns_filters.push($(this).val());
                }
            });
            svcomp_filters.push(unknowns_filters);
        }
        if (svcomp_filters.length == 0) {
            err_notify($('#error___dfc_notype').text());
        }
        else {
            $('#dfc_modal').modal('hide');
            $.redirectPost('/jobs/downloadcompetfile/' + $('#job_pk').val() + '/', {'filters': JSON.stringify(svcomp_filters)});
        }
    });

}


$(document).ready(function () {
    function set_actions_for_run_history() {
        $('#run_history').dropdown();
        var download_conf_btn = $('#download_configuration');
        download_conf_btn.popup();
        download_conf_btn.click(function () {
            window.location.replace('/jobs/download_configuration/' + $('#run_history').val() + '/');
        });
    }
    activate_download_for_compet();
    $('#resources-note').popup();
    $('.for_popup').popup();
    $('#job_scheduler').dropdown();
    var view_job_1st_part = $('#view_job_1st_part');
    view_job_1st_part.find('.ui.dropdown').dropdown();
    $('#remove_job_popup').modal({
        transition: 'fade in', autofocus: false, closable: false})
        .modal('attach events', '#show_remove_job_popup', 'show');
    $('#remove_job_with_children_popup').modal({transition: 'fade in', autofocus: false, closable: false});
    $('#fast_start_job_popup').modal({
        transition: 'fly up', autofocus: false, closable: false})
        .modal('attach events', '#show_fast_job_start_popup', 'show');
    $('#last_start_job_popup').modal({
        transition: 'fly up', autofocus: false, closable: false})
        .modal('attach events', '#show_last_job_start_popup', 'show');
    $('#start_job_popup').modal({
        transition: 'fly up', autofocus: false, closable: false})
        .modal('attach events', '#decide_job_btn_show_popup', 'show');

    $('#clear_verifications_modal').modal({
        transition: 'fly up', autofocus: false, closable: false})
        .modal('attach events', '#clear_verifications_modal_show', 'show');
    $('#cancel_clear_verifications').click(function () {
        $('#clear_verifications_modal').modal('hide');
    });

    $('#collapse_reports_modal').modal({
        transition: 'fly up', autofocus: false, closable: false})
        .modal('attach events', '#collapse_reports_modal_show', 'show');
    $('#cancel_collapse_reports').click(function () {
        $('#collapse_reports_modal').modal('hide');
    });

    $('#cancel_remove_job').click(function () {
        $('#remove_job_popup').modal('hide');
    });
    $('#cancel_remove_job_with_children').click(function () {
        $('#remove_job_with_children_popup').modal('hide');
    });
    $('#cancel_fast_start_job').click(function () {
        $('#fast_start_job_popup').modal('hide');
    });
    $('#cancel_last_start_job').click(function () {
        $('#last_start_job_popup').modal('hide');
    });
    $('#cancel_start_job').click(function () {
        $('#start_job_popup').modal('hide');
    });

    var job_status_popup = $('#job_status_popup');
    if (job_status_popup.length) {
        $('#job_status_popup_activator').popup({
            popup: job_status_popup,
            position: 'bottom center'
        });
    }

    if ($('#edit_job_div').length) {
        $.ajax({
            url: job_ajax_url + 'showjobdata/',
            data: {job_id: $('#job_pk').val()},
            type: 'POST',
            success: function (data) {
                $('#edit_job_div').html(data);
                inittree($('.tree'), 1, 'folder open violet icon', 'folder violet icon');
                set_action_on_file_click();
                set_actions_for_run_history();
            }
        });
    }

    if($('#create_job_global_div').length) {
        set_actions_for_edit_form();
    }

    $('#edit_job_btn').click(function () {
        $('.ui.dinamic.modal').remove();
        $.post(
            job_ajax_url + 'editjob/',
            {job_id: $('#job_pk').val()},
            function (data) {
                $('#edit_job_div').html(data);
                set_actions_for_edit_form();
                $('#cancel_edit_job_btn').click(function () {
                    window.location.replace('');
                });
            }
        );
    });
    $('#collapse_reports_btn').click(function () {
        $('#collapse_reports_modal').modal('hide');
        $('#dimmer_of_page').addClass('active');
        $.post(
            job_ajax_url + 'collapse_reports/',
            {job_id: $('#job_pk').val()},
            function (data) {
                $('#dimmer_of_page').removeClass('active');
                data.error ? err_notify(data.error) : window.location.replace('');
            }
        );
    });

    $('#clear_verifications_confirm').click(function () {
        $('#clear_verifications_modal').modal('hide');
        $('#dimmer_of_page').addClass('active');
        $.post(
            '/reports/ajax/clear_verification_files/',
            {job_id: $('#job_pk').val()},
            function (data) {
                $('#dimmer_of_page').removeClass('active');
                data.error ? err_notify(data.error) : window.location.replace('');
            }
        );
    });

    $("#copy_job_btn").click(function () {
        $.redirectPost('/jobs/create/', {parent_id: $('#job_pk').val()});
    });

    $('#remove_job_btn').click(function () {
        $('#remove_job_popup').modal('hide');
        $.post(
            job_ajax_url + 'do_job_has_children/',
            {job_id: $('#job_pk').val()},
            function (data) {
                if (data.error) {
                    err_notify(data.error);
                    return false;
                }
                if (data.children) {
                    $('#remove_job_with_children_popup').modal('show');
                }
                else {
                    $('#dimmer_of_page').addClass('active');
                    $.post(
                        job_ajax_url + 'removejobs/',
                        {jobs: JSON.stringify([$('#job_pk').val()])},
                        function (data) {
                            $('#dimmer_of_page').removeClass('active');
                            data.error ? err_notify(data.error) : window.location.replace('/jobs/');
                        },
                        'json'
                    );
                }
            },
            'json'
        );
    });
    $('#remove_job_with_children_btn').click(function () {
        $('#remove_job_with_children_popup').modal('hide');
        $('#dimmer_of_page').addClass('active');
        $.post(
            job_ajax_url + 'removejobs/',
            {jobs: JSON.stringify([$('#job_pk').val()])},
            function (data) {
                $('#dimmer_of_page').removeClass('active');
                data.error ? err_notify(data.error) : window.location.replace('/jobs/');
            },
            'json'
        );
    });

    $('#load_job_btn').click(function () {
        window.location.replace(job_ajax_url + 'downloadjob/' + $('#job_pk').val());
    });

    $('#edit_versions').click(function () {
        $.post(
            job_ajax_url + 'getversions/',
            {job_id: $('#job_pk').val()},
            function (data) {
                try {
                    JSON.stringify(data);
                    err_notify(data.message);
                } catch (e) {
                    $('#edit_job_div').html(data);
                    set_actions_for_versions_delete();
                }
            }
        );
    });

    $('#stop_job_btn').click(function () {
        $.post(
            job_ajax_url + 'stop_decision/',
            {job_id: $('#job_pk').val()},
            function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    window.location.replace('');
                }
            }
        );
    });
    $('#fast_job_start').click(function () {
        $.post(
            job_ajax_url + 'fast_run_decision/',
            {job_id: $('#job_pk').val()},
            function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    window.location.replace('');
                }
            }
        );
    });
    $('#lastconf_job_start').click(function () {
        $.post(
            job_ajax_url + 'lastconf_run_decision/',
            {job_id: $('#job_pk').val()},
            function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    window.location.replace('');
                }
            }
        );
    });

    var safe_marks_popup = $('#safe_marks_popup');
    if (safe_marks_popup.length) {
        $('#safe_marks_link').popup({
            popup: safe_marks_popup,
            hoverable: true,
            delay: {show: 100, hide: 300},
            variation: 'wide',
            position: 'right center'
        });
        $('#change_safe_marks').click(function () {
            $('#safe_marks_link').popup('hide');
            $('#dimmer_of_page').addClass('active');
            $.post(
                job_ajax_url + 'enable_safe_marks/',
                {job_id: $('#job_pk').val()},
                function (data) {
                    if (data.error) {
                        $('#dimmer_of_page').removeClass('active');
                        err_notify(data.error);
                    }
                    else {
                        window.location.replace('');
                    }
                }
            );
        });
    }

    $('#upload_reports_popup').modal({transition: 'vertical flip'}).modal('attach events', '#upload_reports_modal_show', 'show');
    $('#upload_reports_file_input').on('fileselect', function () {
        $('#upload_reports_filename').html($('<span>', {text: $(this)[0].files[0].name}));
    });
    $('#upload_reports_cancel').click(function () {
        var file_input = $('#upload_reports_file_input');
        file_input.replaceWith(file_input.clone( true ));
        $('#upload_reports_filename').empty();
        $('#upload_reports_popup').modal('hide');
    });
    $('#upload_reports_start').click(function () {
        var files = $('#upload_reports_file_input')[0].files,
            data = new FormData();
        if (files.length <= 0) {
            err_notify($('#error__no_file_chosen').text());
            return false;
        }
        data.append('archive', files[0]);
        data.append('job_id', $('#job_pk').val());
        $('#upload_reports_popup').modal('hide');
        $('#dimmer_of_page').addClass('active');
        $.ajax({
            url: job_ajax_url + 'upload_reports/',
            type: 'POST',
            data: data,
            dataType: 'json',
            contentType: false,
            processData: false,
            mimeType: 'multipart/form-data',
            xhr: function() {
                return $.ajaxSettings.xhr();
            },
            success: function (data) {
                $('#dimmer_of_page').removeClass('active');
                if ('error' in data) {
                    err_notify(data['error']);
                }
                else {
                    window.location.replace('');
                }
            }
        });
        return false;
    });

    if ($('#job_data_div').length) {
        var num_of_updates = 0, is_filters_open = false, just_status = false, message_is_shown = false;
        $('#job_filters_accordion').accordion({
            onOpen: function() {
                is_filters_open = true;
            },
            onClose: function() {
                is_filters_open = false;
            }
        });
        var interval = setInterval(function () {
            if ($.active > 0) {
                return false;
            }
            if (is_filters_open) {
                return false;
            }
            $.post(
                job_ajax_url + 'get_job_data/',
                {
                    job_id: $('#job_pk').val(),
                    view: collect_view_data('2')['view'],
                    checked_run_history: $('#run_history').val(),
                    just_status: just_status
                },
                function (data) {
                    if (data.error) {
                        err_notify(data.error);
                        return false;
                    }
                    if ('jobdata' in data) {
                        var is_hidden = $('#resources-note').popup('is hidden'), shown_tag_description_id;
                        $('#resources-note').popup('hide');
                        $('.tag-description-popup').each(function () {
                            $(this).popup('hide');
                            if (!$(this).popup('is hidden')) {
                                shown_tag_description_id = $(this).attr('id').replace('tag_description_id_', '')
                            }
                        });
                        $('#job_data_div').html(data['jobdata']);
                        $('#resources-note').popup();
                        if (!is_hidden) {
                            $('#resources-note').popup('show');
                        }
                        $('.tag-description-popup').each(function () {
                            $(this).popup({
                                html: $(this).attr('data-content'), hoverable: true
                            });
                        });
                        if (shown_tag_description_id) {
                            var tag_descr = $('#tag_description_id_' + shown_tag_description_id);
                            if (tag_descr.length) {
                                tag_descr.popup('show');
                            }
                        }
                    }
                    if ('jobstatus' in data) {
                        if (data['jobstatus'] != $('#job_status_value').val()) {
                            window.location.replace('');
                        }
                    }
                    if ('progress' in data) {
                        var tr_before_progress = $('#tr_before_progress');
                        tr_before_progress.nextUntil($('#job_status_popup_activator')).remove();
                        tr_before_progress.after(data['progress']);
                    }
                    num_of_updates++;
                    if (num_of_updates > 60) {
                        if (!message_is_shown) {
                            err_notify($('#error__autoupdate_off').text());
                            message_is_shown = true;
                        }
                        just_status = true;
                    }
                }
            ).fail(function () {
                clearInterval(interval);
            });
        }, 3000);
    }
});
