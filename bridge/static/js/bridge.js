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

window.job_ajax_url = '/jobs/ajax/';
window.marks_ajax_url = '/marks/ajax/';

function getCookie(name) {
    var cookieValue = null;
    if (document.cookie && document.cookie != '') {
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var cookie = $.trim(cookies[i]);
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function csrfSafeMethod(method) {
    return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method))
}

$(document).on('change', '.btn-file :file', function () {
    var input = $(this),
        numFiles = input.get(0).files ? input.get(0).files.length : 1,
        label = input.val().replace(/\\/g, '/').replace(/.*\//, '');
    input.trigger('fileselect', [numFiles, label]);
});

$.ajaxSetup({
    beforeSend: function(xhr, settings) {
        if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
            var csrftoken = getCookie('csrftoken');
            xhr.setRequestHeader("X-CSRFToken", csrftoken);
        }
    }
});
$(document).ajaxError(function () {
    err_notify($('#error__ajax_error').text());
});

$.extend({
    redirectPost: function (location, args) {
        var form = '<input type="hidden" name="csrfmiddlewaretoken" value="' + getCookie('csrftoken') + '">';
        $.each(args, function (key, value) {
            form += '<input type="hidden" name="' + key + '" value=\'' + value + '\'>';
        });
        $('<form action="' + location + '" method="POST">' + form + '</form>').appendTo($(document.body)).submit();
    }
});

jQuery.expr[':'].regex = function(elem, index, match) {
    var matchParams = match[3].split(','),
        validLabels = /^(data|css):/,
        attr = {
            method: matchParams[0].match(validLabels) ?
                        matchParams[0].split(':')[0] : 'attr',
            property: matchParams.shift().replace(validLabels,'')
        },
        regexFlags = 'ig',
        regex = new RegExp(matchParams.join('').replace(/^s+|s+$/g,''), regexFlags);
    return regex.test(jQuery(elem)[attr.method](attr.property));
};

window.err_notify = function (message, duration) {
    var notify_opts = {autoHide: false, style: 'bootstrap', className: 'error'};
    if (!isNaN(duration)) {
        notify_opts['autoHide'] = true;
        notify_opts['autoHideDelay'] = duration;
    }
    $.notify(message, notify_opts);
};

window.success_notify = function (message) {
    $.notify(message, {
        autoHide: true,
        autoHideDelay: 2500,
        style: 'bootstrap',
        className: 'success'
    });
};

window.isASCII = function (str) {
    return /^[\x00-\x7F]*$/.test(str);
};

window.set_actions_for_views = function(filter_type, data_collection) {

    function collect_data() {
        return {
            view: data_collection(),
            view_type: filter_type
        };
    }

    if (!data_collection) {
        return;
    }
    $('#' + filter_type + '__show_unsaved_view_btn').click(function () {
        $.redirectPost('', collect_data());
    });

    $('#' + filter_type + '__save_view_btn').click(function () {
        var view_title = $('#' + filter_type + '__view_name_input').val();
        $.ajax({
            method: 'post',
            url: job_ajax_url + 'check_view_name/',
            dataType: 'json',
            data: {
                view_title: view_title,
                view_type: filter_type
            },
            success: function(data) {
                if (data.error) {
                    err_notify(data.error);
                }
                else {
                    var request_data = collect_data();
                    request_data['title'] = view_title;
                    request_data['view_type'] = filter_type;
                    $.ajax({
                        method: 'post',
                        url: job_ajax_url + 'save_view/',
                        dataType: 'json',
                        data: request_data,
                        success: function(save_data) {
                            if (save_data.error) {
                                err_notify(data.error);
                            }
                            else {
                                $('#' + filter_type + '__available_views').append($('<option>', {
                                    text: save_data['view_name'],
                                    value: save_data['view_id']
                                }));
                                $('#' + filter_type + '__view_name_input').val('');
                                success_notify(save_data.message);
                            }
                        }
                    });
                }
            }
        });
    });

    $('#' + filter_type + '__update_view_btn').click(function () {
        var request_data = collect_data();
        request_data['view_id'] = $('#' + filter_type + '__available_views').children('option:selected').val();
        request_data['view_type'] = filter_type;
        $.ajax({
            method: 'post',
            url: job_ajax_url + 'save_view/',
            dataType: 'json',
            data: request_data,
            success: function(save_data) {
                save_data.error ? err_notify(save_data.error) : success_notify(save_data.message);
            }
        });
    });

    $('#' + filter_type + '__show_view_btn').click(function () {
        $.redirectPost('', {
            view_id: $('#' + filter_type + '__available_views').children('option:selected').val(),
            view_type: filter_type
        });
    });

    $('#' + filter_type + '__remove_view_btn').click(function () {
        $.ajax({
            method: 'post',
            url: job_ajax_url + 'remove_view/',
            dataType: 'json',
            data: {
                view_id: $('#' + filter_type + '__available_views').children('option:selected').val(),
                view_type: filter_type
            },
            success: function(data) {
                if (data.error) {
                    err_notify(data.error)
                }
                else {
                    $('#' + filter_type + '__available_views').children('option:selected').remove();
                    success_notify(data.message)
                }
            }
        });
    });

    $('#' + filter_type + '__prefer_view_btn').click(function () {
        $.ajax({
            method: 'post',
            url: job_ajax_url + 'preferable_view/',
            dataType: 'json',
            data: {
                view_id: $('#' + filter_type + '__available_views').children('option:selected').val(),
                view_type: filter_type
            },
            success: function(data) {
                data.error ? err_notify(data.error) : success_notify(data.message);
            }
        });
    });
};

$(document).ready(function () {
    $('.browse').popup({
        inline: true,
        hoverable: true,
        position: 'bottom left',
        delay: {
            show: 300,
            hide: 600
        }
    });
    $('.ui.checkbox').checkbox();
    $('.ui.accordion').accordion();

    if ($('#show_upload_marks_popup').length) {
        $('#upload_marks_popup').modal('setting', 'transition', 'vertical flip').modal('attach events', '#show_upload_marks_popup', 'show');
    }

    if ($('#show_upload_job_popup').length) {
        $('#upload_job_popup').modal({transition: 'vertical flip', onShow: function () {
            var parent_identifier = $('#job_identifier');
            if (parent_identifier.length) {
                $('#upload_job_parent_id').val(parent_identifier.val());
            }
        }}).modal('attach events', '#show_upload_job_popup', 'show');
    }

    $('#upload_marks_start').click(function () {
        var files = $('#upload_marks_file_input')[0].files,
            data = new FormData();
        if (files.length <= 0) {
            err_notify($('#error__no_file_chosen').text());
            return false;
        }
        for (var i = 0; i < files.length; i++) {
            data.append('file', files[i]);
        }
        $('#upload_marks_popup').modal('hide');
        $('#dimmer_of_page').addClass('active');
        $.ajax({
            url: marks_ajax_url + 'upload_marks/',
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
                if (data.status) {
                    if (data.mark_id.length && data.mark_type.length) {
                        window.location.replace("/marks/" + data.mark_type + "/edit/" + data.mark_id + "/")
                    }
                }
                else {
                    if (data.messages && data.messages.length) {
                        for (var i = 0; i < data.messages.length; i++) {
                            var err_message = data.messages[i][0] + ' (' + data.messages[i][1] + ')';
                            err_notify(err_message);
                        }
                    }
                    else if (data.message && data.message.length) {
                        err_notify(data.message);
                    }
                }
            }
        });
    });

    $('#upload_marks_cancel').click(function () {
        var file_input = $('#upload_marks_file_input');
        file_input.replaceWith(file_input.clone(true));
        $('#upload_marks_filename').empty();
        $('#upload_marks_popup').modal('hide');
    });

    $('#upload_marks_file_input').on('fileselect', function () {
        var files = $(this)[0].files,
            filename_list = $('<ul>');
        for (var i = 0; i < files.length; i++) {
            filename_list.append($('<li>', {text: files[i].name}));
        }
        $('#upload_marks_filename').html(filename_list);
    });

    $('#upload_job_file_input').on('fileselect', function () {
        var files = $(this)[0].files,
            filename_list = $('<ul>');
        for (var i = 0; i < files.length; i++) {
            filename_list.append($('<li>', {text: files[i].name}));
        }
        $('#upload_job_filename').html(filename_list);
    });

    $('#upload_job_cancel').click(function () {
        var file_input = $('#upload_job_file_input');
        file_input.replaceWith(file_input.clone( true ));
        $('#upload_job_parent_id').val('');
        $('#upload_job_filename').empty();
        $('#upload_job_popup').modal('hide');
    });

    $('#upload_jobs_start').click(function () {
        var parent_id = $('#upload_job_parent_id').val();
        if (parent_id.length == 0) {
            err_notify($('#error__parent_required').text());
            return false;
        }
        var files = $('#upload_job_file_input')[0].files,
            data = new FormData();
        if (files.length <= 0) {
            err_notify($('#error__no_file_chosen').text());
            return false;
        }
        for (var i = 0; i < files.length; i++) {
            data.append('file', files[i]);
        }
        $('#upload_job_popup').modal('hide');
        $('#dimmer_of_page').addClass('active');
        $.ajax({
            url: job_ajax_url + 'upload_job/' + encodeURIComponent(parent_id) + '/',
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
                else if ('errors' in data) {
                    for (var i = 0; i < data['errors'].length; i++) {
                        err_notify(data['errors'][i]);
                    }
                }
                else {
                    window.location.replace('');
                }
            }
        });
        return false;
    });
    $('.tag-description-popup').each(function () {
        $(this).popup({
            html: $(this).attr('data-content'),
            hoverable: true
        });
    });
    $('.simple-popup').each(function () {
        $(this).popup({
            text: $(this).attr('data-content')
        });
    });
});