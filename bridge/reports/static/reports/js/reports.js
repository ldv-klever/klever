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
    $('#resources-note').popup();
    $('#component_name_tr').popup({
        popup: $('#timeinfo_popup'),
        position: 'right center',
        hoverable: true,
        delay: {
            show: 100,
            hide: 300
        }
    });
    $('#computer_description_tr').popup({
        popup: $('#computer_info_popup'),
        position: 'right center',
        hoverable: true,
        delay: {
            show: 100,
            hide: 300
        }
    });

    $('.report-data-popup').each(function () {
        $(this).popup({
            html: $(this).attr('data-content'),
            position: 'right center',
            hoverable: $(this).hasClass('hoverable')
        });
    });

    $('.parent-popup').popup({inline:true});
    $('.ui.dropdown').dropdown();

    $('#file_content_modal').modal('setting', 'transition', 'fade');
    $('#show_component_log').click(function () {
        var report_id = $('#report_pk').val();
        $.ajax({
            url: '/reports/logcontent/' + report_id + '/',
            type: 'GET',
            success: function (data) {
                $('#file_content').text(data);
                $('#download_file_href').attr('href', '/reports/log/' + report_id + '/');
                $('#file_content_modal').modal('show');
                $('#close_file_view').click(function () {
                    $('#file_content_modal').modal('hide');
                    $('#file_content').empty();
                    $('#download_file_href').attr('href', '#');
                });
            }
        });
    });

    $('.attr-data-href').click(function (event) {
        event.preventDefault();
        var attr_id = $(this).data('attr-id');
        $.ajax({
            url: '/reports/attrdata-content/' + attr_id + '/',
            type: 'GET',
            success: function (data) {
                $('#file_content').text(data);
                $('#download_file_href').attr('href', '/reports/attrdata/' + attr_id + '/');
                $('#file_content_modal').modal('show');
                $('#close_file_view').click(function () {
                    $('#file_content_modal').modal('hide');
                    $('#file_content').empty();
                    $('#download_file_href').attr('href', '#');
                });
            }
        });
    });

    function activate_inline_markform(data) {
        var markform = $('#inline_mark_form');
        markform.html(data);
        activate_tags();
        markform.find('.ui.checkbox').checkbox();
        markform.show();
        $('#cancel_create_mark').click(function () {
            $('#inline_mark_form').hide().empty();
        });
        $('#save_inline_mark_btn').click(function () {
            $('#dimmer_of_page').addClass('active');
            var data, mark_id = $('#mark_pk');
            if (mark_id.length) {
                data = {savedata: collect_markdata(), mark_id: mark_id.val()}
            }
            else {
                data = {savedata: collect_new_markdata()}
            }
            $.post(
                marks_ajax_url + 'save_mark/',
                data,
                function (data) {
                    if (data.error) {
                        $('#dimmer_of_page').removeClass('active');
                        err_notify(data.error);
                    }
                    else if ('cache_id' in data) {
                        window.location.href = '/marks/association_changes/' + data['cache_id'] + '/';
                    }
                }
            );
        });
    }

    $('#create_light_mark_btn').click(function () {
        $.post(
            marks_ajax_url + 'inline_mark_form/',
            {
                report_id: $('#report_pk').val(),
                type: $('#report_type').val()
            },
            function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else if ('data' in data) {
                    activate_inline_markform(data['data']);
                }
            }
        );
    });

    $('button[id^="inline_edit_mark_"]').click(function () {
        $.post(
            marks_ajax_url + 'inline_mark_form/',
            {
                mark_id: $(this).attr('id').replace('inline_edit_mark_', ''),
                type: $('#report_type').val()
            },
            function (data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else if ('data' in data) {
                    activate_inline_markform(data['data']);
                }
            }
        );
    });
    $('#show_leaf_attributes').click(function () {
        var attr_table = $('#leaf_attributes');
        if (attr_table.is(':hidden')) {
            attr_table.show();
        }
        else {
            attr_table.hide();
        }
    });
    $('button[id^="unconfirm_association_"]').click(function () {
        $.post(
            marks_ajax_url + 'unconfirm-association/',
            {
                mark_id: $(this).attr('id').replace('unconfirm_association_', ''),
                report_id: $('#report_pk').val(),
                report_type: $('#report_type').val()
            },
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
    $('button[id^="confirm_association_"]').click(function () {
        $.post(
            marks_ajax_url + 'confirm-association/',
            {
                mark_id: $(this).attr('id').replace('confirm_association_', ''),
                report_id: $('#report_pk').val(),
                report_type: $('#report_type').val()
            },
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
    $('.like-popup').popup({
        hoverable: true,
        position: 'top right'
    });

    $('button[id^="like_association_"]').click(function () {
        $.post(
            marks_ajax_url + 'like-association/',
            {
                mark_id: $(this).attr('id').replace('like_association_', ''),
                report_id: $('#report_pk').val(),
                report_type: $('#report_type').val(),
                dislike: false
            },
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
    $('button[id^="dislike_association_"]').click(function () {
        $.post(
            marks_ajax_url + 'like-association/',
            {
                mark_id: $(this).attr('id').replace('dislike_association_', ''),
                report_id: $('#report_pk').val(),
                report_type: $('#report_type').val(),
                dislike: true
            },
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
});

