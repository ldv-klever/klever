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

$(document).ready(function () {
    drow_connections();
    init_popups();
    var create_root_btn = $('#create_root_tag');
    create_root_btn.popup();

    // Clear data in create/edit modals
    function clear_modal() {
        $('#edit_tag_id').val('');
        $('#tag_name').val('');
        $('#tag_description').val('');
        $('#create_tag_name').val('');
        $('#create_tag_description').val('');
        $('#tag_parent').children().each(function () {
            if ($(this).val() != 0) {
                $(this).remove();
            }
        });
        $('#create_tag_parent').children().each(function () {
            if ($(this).val() != 0) {
                $(this).remove();
            }
        });
        $('#create_tag_user_access_selection').empty();
        $('#edit_tag_user_access_selection').empty();
    }
    function create_access_selections(access, user_access_field) {
        if (user_access_field.length && access['all'].length > 0) {
            var new_dropdown1 = $('<select>', {multiple: true, 'class': 'ui fluid dropdown', 'id': 'user_access_edit_sel'}),
                new_dropdown2 = $('<select>', {multiple: true, 'class': 'ui fluid dropdown', 'id': 'user_access_child_sel'});
            $.each(access['all'], function (i, v) {
                if (access['access_edit'].indexOf(v[0]) >= 0) {
                    new_dropdown1.append($('<option>', {value: v[0], text: v[1], selected: true}));
                }
                else {
                    new_dropdown1.append($('<option>', {value: v[0], text: v[1]}));
                }
            });
            $.each(access['all'], function (i, v) {
                if (access['access_child'].indexOf(v[0]) >= 0) {
                    new_dropdown2.append($('<option>', {value: v[0], text: v[1], selected: true}));
                }
                else {
                    new_dropdown2.append($('<option>', {value: v[0], text: v[1]}));
                }
            });
            user_access_field.append($('<label>', {'for': 'user_access_edit_sel', 'class': 'bold-text', 'text': $('#label_for_user_access_1').text()}));
            user_access_field.append(new_dropdown1);
            user_access_field.append($('<br>'));
            user_access_field.append($('<label>', {'for': 'user_access_child_sel', 'class': 'bold-text', 'text': $('#label_for_user_access_2').text()}));
            user_access_field.append($('<br>'));
            user_access_field.append(new_dropdown2);
            user_access_field.find('select').dropdown();
        }
    }

    var remove_tag_icon = $('.remove-tag-icon'),
        create_tag_icon = $('.create-tag-icon'),
        edit_tag_icon = $('.edit-tag-icon');

    /*************
    * Remove Tag *
    *************/
    remove_tag_icon.hover(function () {
        $(this).parent().children('.icon-text-remove').first().show();
    }, function () {
        $(this).parent().children('.icon-text-remove').first().hide();
    });
    var remove_tag_modal = $('#remove_tag_modal');
    remove_tag_modal.modal({transition: 'fly up', autofocus: false, closable: false});
    remove_tag_icon.click(function () {
        $('.edit-tag-cell').popup('hide');
        $('#edit_tag_id').val($(this).parent().attr('id').replace('tag_popup_', ''));
        remove_tag_modal.modal('show');
    });
    $('#confirm_remove_tag').click(function () {
        $.ajax('/marks/tags/' + $('#tags_type').text() + '/delete/' + $('#edit_tag_id').val() + '/', {}, function (data) {
            if (data.error) {
                remove_tag_modal.modal('hide');
                clear_modal();
                err_notify(data.error);
                return false;
            }
            window.location.replace('');
        });
    });
    $('#cancel_remove_tag').click(function () {
        remove_tag_modal.modal('hide');
        clear_modal();
    });

    /***********
    * Edit Tag *
    ***********/
    var edit_tag_modal = $('#edit_tag_modal'), parent_dropdown = $('#tag_parent');
    parent_dropdown.dropdown();
    edit_tag_modal.modal({transition: 'drop', autofocus: false, closable: false});

    $('#cancel_edit_tag').click(function () {
        edit_tag_modal.modal('hide');
        clear_modal();
    });
    edit_tag_icon.hover(function () {
        $(this).parent().children('.icon-text-edit').first().show();
    }, function () {
        $(this).parent().children('.icon-text-edit').first().hide();
    });
    edit_tag_icon.click(function () {
        var tag_popup = $(this).parent(), tag_id = tag_popup.attr('id').replace('tag_popup_', '');
        $('#tag_name').val($('#tag_id_' + tag_id).text());
        $('#tag_description').val(tag_popup.children('.content').first().html());
        $.post('/marks/tags/' + $('#tags_type').text() + '/get_tag_data/', {tag_id: tag_id}, function (data) {
            if (data.error) {
                err_notify(data.error);
                clear_modal();
                return false;
            }
            if (data['current'] != '0') {
                parent_dropdown.append($('<option>', {'value': data['current'], 'text': $('#tag_id_' + data['current']).text(), selected: true}));
            }
            $.each(JSON.parse(data['parents']), function (i, value) {
                parent_dropdown.append($('<option>', {'value': value, 'text': $('#tag_id_' + value).text()}));
            });
            $('#edit_tag_id').val(tag_id);
            create_access_selections(JSON.parse(data['access']), $('#edit_tag_user_access_selection'));

            $('.edit-tag-cell').popup('hide');
            edit_tag_modal.modal('show');

            parent_dropdown.dropdown('refresh');
            setTimeout(function () {
                parent_dropdown.dropdown('set selected', parent_dropdown.val());
            }, 1);
        });
    });
    $('#save_tag').click(function () {
        var uadiv = $('#edit_tag_user_access_selection'), access = {
            'edit': uadiv.find('#user_access_edit_sel').val(),
            'child': uadiv.find('#user_access_child_sel').val()
        };
        $.ajax({
            url: '/marks/tags/save_tag/',
            type: 'POST',
            data: {
                name: $('#tag_name').val(),
                tag_id: $('#edit_tag_id').val(),
                tag_type: $('#tags_type').text(),
                description: $('#tag_description').val(),
                parent_id: $('#tag_parent').val(),
                action: 'edit',
                access: JSON.stringify(access)
            },
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                    return false;
                }
                window.location.replace('');
            }
        });
    });

    /*************
    * Create Tag *
    *************/
    create_tag_icon.hover(function () {
        $(this).parent().children('.icon-text-create').first().show();
    }, function () {
        $(this).parent().children('.icon-text-create').first().hide();
    });

    var create_tag_modal = $('#create_tag_modal'), create_tag_parent = $('#create_tag_parent');
    create_tag_modal.modal({transition: 'drop', autofocus: false, closable: false});
    function create_tag_click(parent_id) {
        $.post('/marks/tags/' + $('#tags_type').text() + '/get_tag_data/', {}, function (data) {
            if (data.error) {
                err_notify(data.error);
                clear_modal();
                return false;
            }
            $.each(JSON.parse(data['parents']), function (i, value) {
                var dropdown_option_data = {'value': value, 'text': $('#tag_id_' + value).text()};
                if (value == parent_id) {
                    dropdown_option_data['selected'] = true;
                }
                create_tag_parent.append($('<option>', dropdown_option_data));
            });
            create_tag_parent.dropdown('refresh');
            setTimeout(function () {
                create_tag_parent.dropdown('set selected', create_tag_parent.val());
            }, 1);
            create_access_selections(JSON.parse(data['access']), $('#create_tag_user_access_selection'));

            $('.edit-tag-cell').popup('hide');
            create_tag_modal.modal('show');
        });
    }
    create_root_btn.click(function () {
        create_tag_click(0);
    });
    create_tag_icon.click(function () {
        create_tag_click($(this).parent().attr('id').replace('tag_popup_', ''));
    });
    $('#cancel_create_tag').click(function () {
        create_tag_modal.modal('hide');
        clear_modal();
    });
    $('#confirm_create_tag').click(function () {
        var uadiv = $('#create_tag_user_access_selection'), access = {
            'edit': uadiv.find('#user_access_edit_sel').val(),
            'child': uadiv.find('#user_access_child_sel').val()
        };
        $.ajax({
            url: '/marks/tags/save_tag/',
            type: 'POST',
            data: {
                name: $('#create_tag_name').val(),
                tag_type: $('#tags_type').text(),
                description: $('#create_tag_description').val(),
                parent_id: $('#create_tag_parent').val(),
                action: 'create',
                access: JSON.stringify(access)
            },
            success: function (data) {
                if (data.error) {
                    err_notify(data.error);
                    return false;
                }
                window.location.replace('');
            }
        });
    });
    $('#download_all_tags').popup();

    $('#upload_tags').popup();
    $('#upload_tags_modal').modal('setting', 'transition', 'vertical flip').modal('attach events', '#upload_tags', 'show');
    $('#upload_tags_start').click(function () {
        var files = $('#upload_tags_file_input')[0].files, data = new FormData();
        if (files.length <= 0) {
            err_notify($('#error__no_file_chosen').text());
            return false;
        }
        data.append('file', files[0]);
        $('#upload_tags_modal').modal('hide');
        $('#dimmer_of_page').addClass('active');
        $.ajax({
            url: '/marks/tags/' + $('#tags_type').text() + '/upload/',
            type: 'POST',
            data: data,
            dataType: 'json',
            contentType: false,
            processData: false,
            mimeType: 'multipart/form-data',
            xhr: function() { return $.ajaxSettings.xhr() },
            success: function (data) {
                $('#dimmer_of_page').removeClass('active');
                data.error ? err_notify(data.error) : window.location.replace('');
            }
        });
    });
    $('#upload_tags_cancel').click(function () {
        $('#upload_tags_modal').modal('hide');
    });
    $('#upload_tags_file_input').on('fileselect', function () {
        var files = $(this)[0].files,
            filename_list = $('<ul>');
        for (var i = 0; i < files.length; i++) {
            filename_list.append($('<li>', {text: files[i].name}));
        }
        $('#upload_tags_filename').html(filename_list);
    });
});