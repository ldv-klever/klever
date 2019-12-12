/*
 * Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
 * Ivannikov Institute for System Programming of the Russian Academy of Sciences
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

jQuery(function () {

    // Draw connections
    $('.tag-tree-link').each(function () {
        let for_style = [];
        $.each($(this).data('links').split(''), function (a, img_t) {
            for_style.push("url('/static/marks/css/images/L_" + img_t + ".png') center no-repeat");
        });
        if (for_style.length) $(this).attr('style', "background: " + for_style.join(',') + ';');
    });

    // Initialize popups
    $('.tag-popup').each(function () {
        $('#tag__' + $(this).data('tag')).popup({
            popup: $(this),
            hoverable: true,
            position: 'top left',
            exclusive: true,
            delay: {show: 100, hide: 300},
            variation: 'very wide'
        })
    });

    let tags_type = $('#tags_type').text(),
        tags_base_url = '/marks/api/tags/' + tags_type + '/';

    /*************
    * Remove Tag *
    *************/
    let remove_tag_icon = $('.remove-tag-icon'),
        remove_tag_modal = $('#remove_tag_modal');
    remove_tag_icon.hover(function () {
        $(this).parent().children('.icon-text-remove').first().show();
    }, function () {
        $(this).parent().children('.icon-text-remove').first().hide();
    });
    remove_tag_modal.modal({transition: 'fly up', autofocus: false, closable: false});

    remove_tag_icon.click(function () {
        // Hide popup first
        $('.edit-tag-cell').popup('hide');

        let tag_id = $(this).closest('.tag-popup').data('tag');
        remove_tag_modal.find('.modal-confirm').data('tag', tag_id);
        remove_tag_modal.modal('show');
    });
    remove_tag_modal.find('.modal-confirm').click(function () {
        $.ajax({
            url: tags_base_url + $(this).data('tag') + '/',
            type: 'DELETE',
            success: function() {
                window.location.replace('');
            }
        });
    });
    remove_tag_modal.find('.modal-cancel').click(function () {
        remove_tag_modal.modal('hide')
    });

    /***********
    * Edit Tag *
    ***********/
    let edit_tag_icon = $('.edit-tag-icon'),
        edit_tag_modal = $('#edit_tag_modal');
    $('#edit_tag_parent').dropdown();
    edit_tag_icon.hover(function () {
        $(this).parent().children('.icon-text-edit').first().show();
    }, function () {
        $(this).parent().children('.icon-text-edit').first().hide();
    });
    edit_tag_modal.modal({transition: 'drop', autofocus: false, closable: false});

    edit_tag_icon.click(function () {
        let tag_id = $(this).closest('.tag-popup').data('tag');
        $.ajax({
            url: tags_base_url + tag_id + '/',
            type: 'GET',
            success: function(resp) {
                $('#edit_tag_name').val(resp['name']);
                $('#edit_tag_description').val(resp['description']);

                let parent_dropdown = $('#edit_tag_parent');
                parent_dropdown.empty();
                $.each(resp['parents'], function (i, value) {
                    let option_data = {'value': value['id'], 'text': value['name']};
                    if (value['id'] === resp['parent']) option_data['selected'] = true;
                    parent_dropdown.append($('<option>', option_data));
                });
                edit_tag_modal.find('.modal-confirm').data('tag', tag_id);
                edit_tag_modal.modal('show');
                parent_dropdown.dropdown('refresh');
                setTimeout(function () {
                    parent_dropdown.dropdown('set selected', parent_dropdown.val());
                }, 1);
            }
        });
    });
    edit_tag_modal.find('.modal-cancel').click(function () {
        edit_tag_modal.modal('hide')
    });
    edit_tag_modal.find('.modal-confirm').click(function () {
        let tag_id = $(this).data('tag'), parent = $('#edit_tag_parent').val();
        if (parent === '0') parent = null;
        $.ajax({
            url: tags_base_url + tag_id + '/',
            type: 'PUT',
            data: JSON.stringify({
                name: $('#edit_tag_name').val(),
                parent: parent,
                description: $('#edit_tag_description').val()
            }),
            dataType: "json", contentType: "application/json",
            success: function () {
                window.location.replace('')
            }
        });
    });

    /*********************
    * Change user access *
    **********************/
    let users_tag_icon = $('.change-access-tag-icon'),
        users_tag_modal = $('#change_access_tag_modal');
    users_tag_icon.hover(function () {
        $(this).parent().children('.icon-text-change-access').first().show();
    }, function () {
        $(this).parent().children('.icon-text-change-access').first().hide();
    });
    users_tag_modal.modal({transition: 'drop', autofocus: false, closable: false});

    users_tag_icon.click(function () {
        // Hide popup first
        $('.edit-tag-cell').popup('hide');

        let tag_id = $(this).closest('.tag-popup').data('tag');
        users_tag_modal.find('.modal-confirm').data('tag', tag_id);

        $.get('/marks/api/tags-access/' + tags_type + '/' + tag_id + '/', {}, function (resp) {
            let edit_selector = $('#change_access_edit_select'),
                create_selector = $('#change_access_create_select');
            edit_selector.empty();
            create_selector.empty();
            $.each(resp, function (i, user_data) {
                edit_selector.append($('<option>', {
                    value: user_data['id'],
                    text: user_data['name'],
                    selected: user_data['can_edit']
                }));
                create_selector.append($('<option>', {
                    value: user_data['id'],
                    text: user_data['name'],
                    selected: user_data['can_create']
                }));
            });

            edit_selector.dropdown('refresh');
            create_selector.dropdown('refresh');
            setTimeout(function () {
                let edit_value = edit_selector.val(), create_value = create_selector.val();
                edit_value ? edit_selector.dropdown('set selected', edit_value) : edit_selector.dropdown('clear');
                create_value ? create_selector.dropdown('set selected', create_value) : create_selector.dropdown('clear');
            }, 1);

            users_tag_modal.modal('show');
        }, 'json');
    });
    users_tag_modal.find('.modal-confirm').click(function () {
        $.ajax({
            url: '/marks/api/tags-access/' + tags_type + '/' + $(this).data('tag') + '/',
            type: 'POST',
            dataType: "json", contentType: "application/json",
            data: JSON.stringify({
                can_edit: $('#change_access_edit_select').val(),
                can_create: $('#change_access_create_select').val()
            }),
            success: function () {
                success_notify($('#api_success_message').text())
            }
        });
    });
    users_tag_modal.find('.modal-cancel').click(function () {
        users_tag_modal.modal('hide')
    });

    /*************
    * Create Tag *
    **************/
    let create_tag_icon = $('.create-tag-icon'),
        create_tag_modal = $('#create_tag_modal');
    $('#create_tag_parent').dropdown();
    create_tag_icon.hover(function () {
        $(this).parent().children('.icon-text-create').first().show();
    }, function () {
        $(this).parent().children('.icon-text-create').first().hide();
    });
    create_tag_modal.modal({transition: 'drop', autofocus: false, closable: false});

    create_tag_icon.click(function () {
        let tag_id = $(this).closest('.tag-popup').data('tag');
        $.ajax({
            url: tags_base_url + tag_id + '/',
            type: 'GET',
            success: function(resp) {
                $('#create_tag_name').val('');
                $('#create_tag_description').val('');

                $('#create_tag_parent').text(resp['name']);
                create_tag_modal.find('.modal-confirm').data('tag', tag_id);
                create_tag_modal.modal('show');
            }
        });
    });
    create_tag_modal.find('.modal-cancel').click(function () {
        create_tag_modal.modal('hide')
    });
    create_tag_modal.find('.modal-confirm').click(function () {
        let tag_id = $(this).data('tag');
        $.ajax({
            url: tags_base_url,
            type: 'POST',
            data: JSON.stringify({
                name: $('#create_tag_name').val(),
                parent: tag_id,
                description: $('#create_tag_description').val()
            }),
            dataType: "json", contentType: "application/json",
            success: function () {
                window.location.replace('')
            }
        });
    });

    // Creating root tag
    $('#create_root_tag').click(function () {
        $('#create_tag_name').val('');
        $('#create_tag_description').val('');
        $('#create_tag_parent').text('-');
        create_tag_modal.find('.modal-confirm').data('tag', null);
        create_tag_modal.modal('show');
    });

    /*************************
     * Upload tags from file *
     *************************/
    let upload_tags_modal = $('#upload_tags_modal');
    upload_tags_modal.modal('setting', 'transition', 'vertical flip').modal('attach events', '#upload_tags', 'show');
    upload_tags_modal.find('.modal-confirm').click(function () {
        let data = new FormData(), files = $('#upload_tags_file_input')[0].files;
        if (files.length <= 0) return err_notify($('#error__no_file_chosen').text());
        data.append('file', files[0]);
        upload_tags_modal.modal('hide');
        $('#dimmer_of_page').addClass('active');
        $.ajax({
            url: '/marks/api/tags-upload/' + tags_type + '/',
            type: 'POST',
            data: data,
            // dataType: 'json',
            cache: false,
            contentType: false,
            processData: false,
            mimeType: 'multipart/form-data',
            xhr: function() { return $.ajaxSettings.xhr() },
            success: function () {
                window.location.replace('')
            }
        });
    });
    upload_tags_modal.find('.modal-cancel').click(function () {
        upload_tags_modal.modal('hide')
    });
    $('#upload_tags_file_input').on('fileselect', function () {
        $('#upload_tags_filename').text($(this)[0].files[0].name)
    });
});
