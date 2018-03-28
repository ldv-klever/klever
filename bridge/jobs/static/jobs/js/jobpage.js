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
                    if (data.error) {
                        err_notify(data.error);
                    }
                    else {
                        close_fileview_btn.unbind();
                        close_fileview_btn.click(function (event) {
                            event.preventDefault();
                            $('#file_content_modal').modal('hide');
                            $('#file_content').empty();
                        });
                        download_file_btn.unbind();
                        download_file_btn.click(function(event) {
                            event.preventDefault();
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

    $('#view_versions').click(get_versions);

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
