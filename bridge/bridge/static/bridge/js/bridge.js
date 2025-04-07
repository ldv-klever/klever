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

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        let cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            let cookie = cookies[i].trim();
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
    let input = $(this),
        numFiles = input.get(0).files ? input.get(0).files.length : 1,
        label = input.val().replace(/\\/g, '/').replace(/.*\//, '');
    input.trigger('fileselect', [numFiles, label]);
});

$.ajaxSetup({
    beforeSend: function(xhr, settings) {
        if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
            xhr.setRequestHeader("X-CSRFToken", getCookie('csrftoken'));
        }
    }
});
$(document).ajaxError(function (xhr, err) {
    $('#dimmer_of_page').removeClass('active');
    if (err['responseJSON']) {
        if (err['responseJSON'].error) err_notify(err['responseJSON'].error);
        else if (err['responseJSON'].detail) err_notify(err['responseJSON'].detail);
        else {
            let errors = flatten_api_errors(err['responseJSON']);
            if (errors.length) {
                $.each(errors, function (i, value) {
                    err_notify(value)
                });
            }
            else err_notify($('#error__ajax_error').text());
        }
    }
    else {
        err_notify($('#error__ajax_error').text());
    }
});

window.flatten_api_errors = function(data, labels) {
    let errors_arr = [];

    function get_label(key) {
        return (key && labels && labels[key]) ? labels[key] : null;
    }

    function get_children_messages(obj, err_key) {
        if (Array.isArray(obj)) {
            $.each(obj, function (i, value) {
                get_children_messages(value, err_key);
            });
        }
        else if (typeof obj === 'object') {
            $.each(obj, function (key, value) {
                get_children_messages(value, key);
            });
        }
        else {
            let error_text = obj + '', label = get_label(err_key);
            if (label) error_text = '{0}: {1}'.format(label, error_text);
            if (errors_arr.indexOf(error_text) < 0) errors_arr.push(error_text);
        }
    }

    get_children_messages(data);

    return errors_arr;
};

jQuery.expr[':'].regex = function(elem, index, match) {
    let matchParams = match[3].split(','),
        validLabels = /^(data|css):/,
        attr = {
            method: matchParams[0].match(validLabels) ? matchParams[0].split(':')[0] : 'attr',
            property: matchParams.shift().replace(validLabels,'')
        },
        regexFlags = 'ig',
        regex = new RegExp(matchParams.join('').replace(/^s+|s+$/g,''), regexFlags);
    return regex.test(jQuery(elem)[attr.method](attr.property));
};

window.err_notify = function (message, duration) {
    let notify_opts = {autoHide: false, style: 'bootstrap', className: 'error'};
    if (!isNaN(duration)) {
        notify_opts['autoHide'] = true;
        notify_opts['autoHideDelay'] = duration;
    }
    $.notify(message, notify_opts);
    return false;
};

window.warn_notify = function (message, duration) {
    let notify_opts = {autoHide: false, style: 'bootstrap', className: 'warn'};
    if (!isNaN(duration)) {
        notify_opts['autoHide'] = true;
        notify_opts['autoHideDelay'] = duration;
    }
    $.notify(message, notify_opts);
    return false;
};

window.success_notify = function (message, duration) {
    let notify_opts = {autoHide: false, style: 'bootstrap', className: 'success'};
    if (!isNaN(duration)) {
        notify_opts['autoHide'] = true;
        notify_opts['autoHideDelay'] = duration;
    }
    $.notify(message, notify_opts);
    return true;
};

window.isASCII = function (str) {
    return /^[\x00-\x7F]*$/.test(str);
};

window.encodeQueryData = function(data) {
    return Object.keys(data).map(function(key) {
        return [key, data[key]].map(encodeURIComponent).join("=");
    }).join("&");
};

window.api_send_json = function(url, method, data, on_success, on_error) {
    $.ajax({
        url: url, method: method,
        data: JSON.stringify(data),
        contentType: "application/json; charset=utf-8",
        dataType: 'json',
        crossDomain: false,
        success: on_success,
        error: on_error
    });
};

window.api_upload_file = function(url, method, data, on_success) {
    $('#dimmer_of_page').addClass('active');
    $.ajax({
        url: url,
        method: method,
        data: data,
        dataType: 'json',
        contentType: false,
        processData: false,
        mimeType: 'multipart/form-data',
        xhr: function() { return $.ajaxSettings.xhr() },
        success: on_success
    });
};

window.collect_view_data = function(view_type) {
    let data = {};
    $('input[id^="view_data_' + view_type + '__"]').each(function () {
        let data_name = $(this).attr('id').replace('view_data_' + view_type + '__', ''), data_type = $(this).val();

        if (data_type === 'checkboxes') {
            data[data_name] = [];
            $('input[id^="view_' + view_type + '__' + data_name + '__"]').each(function () {
                if ($(this).is(':checked')) {
                    data[data_name].push($(this).attr('id').replace('view_' + view_type + '__' + data_name + '__', ''));
                }
            });
        }
        else if (data_type === 'list') {
            data[data_name] = [];
            $.each($(this).data('list').split('__'), function (i, val) {
                if (val.startsWith('radio_')) {
                    data[data_name].push($('input[name="view_' + view_type + '__' + val + '"]:checked').val());
                }
                else {
                    let element_value = $('#view_' + view_type + '__' + val).val();
                    if (!element_value.length) {
                        delete data[data_name];
                        return false;
                    }
                    data[data_name].push(element_value);
                }
            });
        }
        else if (data_type === 'list_null') {
            data[data_name] = [];
            $.each($(this).data('list').split('__'), function (i, val) {
                if (val.startsWith('radio_')) {
                    data[data_name].push($('input[name="view_' + view_type + '__' + val + '"]:checked').val());
                }
                else {
                    data[data_name].push($('#view_' + view_type + '__' + val).val());
                }
            });
        }
        else if (data_type.startsWith('checkboxes_if_')) {
            if ($('#view_condition_' + view_type + '__' + data_type.replace('checkboxes_if_', '')).is(':checked')) {
                data[data_name] = [];
                $('input[id^="view_' + view_type + '__' + data_name + '__"]').each(function () {
                    if ($(this).is(':checked')) {
                        data[data_name].push($(this).attr('id').replace('view_' + view_type + '__' + data_name + '__', ''));
                    }
                });
            }
        }
        else if (data_type.startsWith('list_if_')) {
            if ($('#view_condition_' + view_type + '__' + data_type.replace('list_if_', '')).is(':checked')) {
               data[data_name] = [];
                $.each($(this).data('list').split('__'), function (i, val) {
                    if (val.startsWith('radio_')) {
                        data[data_name].push($('input[name="view_' + view_type + '__' + val + '"]:checked').val());
                    }
                    else {
                        let element_value = $('#view_' + view_type + '__' + val).val();
                        if (!element_value.length) {
                            delete data[data_name];
                            return false;
                        }
                        data[data_name].push(element_value);
                    }
                });
            }
        }
        else if (data_type === 'multiselect') {
            data[data_name] = [];
            $('#view_' + view_type + '__' + data_name).children('option').each(function () {
                data[data_name].push($(this).val());
            });
        }
    });
    return {view: JSON.stringify(data), view_type: view_type};
};

window.set_actions_for_views = function(view_type) {

    function clear_query_params(url) {
        $.each(['page', 'view', 'view_id', 'view_type'], function (i, get_param) {
            let re = new RegExp('(' + get_param + '=).*?(&|$)');
            if (url.indexOf(get_param + "=") > -1) url = url.replace(re, '')
        });
        if (url.indexOf('?') > -1) {
            let last_char = url.slice(-1);
            if (last_char !== '&' && last_char !== '?') url += '&';
        }
        else url += '?';
        return url;
    }

    $('#view_show_unsaved_btn__' + view_type).click(function () {
        window.location.href = clear_query_params(window.location.href) + encodeQueryData(collect_view_data(view_type));
    });

    $('#view_save_btn__' + view_type).click(function () {
        let view_data = collect_view_data(view_type);
        $.ajax({
            method: 'POST',
            url: '/users/views/',
            // dataType: 'json',
            data: {
                view: view_data['view'], type: view_data['view_type'],
                name: $('#view_name_input__' + view_type).val()
            },
            success: function (resp) {
                $('#view_list__' + view_type).append($('<option>', {text: resp['name'], value: resp['id']}));
                $('#view_name_input__' + view_type).val('');
                success_notify($('#view_save_message__' + view_type).text());
            }
        });
    });

    $('#view_update_btn__' + view_type).click(function () {
        let view_id = $('#view_list__' + view_type).val();
        if (view_id === 'default') return err_notify($('#view_default_error__' + view_type).text());
        let view_data = collect_view_data(view_type);

        $.ajax({
            url: `/users/views/${view_id}/`,
            method: 'PATCH',
            data: {view: view_data['view']},
            success: function() {
                success_notify($('#view_save_message__' + view_type).text())
            }
        });
    });

    $('#view_show_btn__' + view_type).click(function () {
        let query_params = {view_id: $('#view_list__' + view_type).val(), view_type: view_type};
        window.location.href = clear_query_params(window.location.href) + encodeQueryData(query_params);
    });

    $('#view_remove_btn__' + view_type).click(function () {
        $.ajax({
            url: `/users/views/${$('#view_list__' + view_type).val()}/`,
            method: 'DELETE',
            success: function() {
                $('#view_list__' + view_type).children('option:selected').remove();
                success_notify($('#view_deleted_message__' + view_type).text())
            }
        });
    });
    $('#view_share_btn__' + view_type).click(function () {
        let selected_view = $('#view_list__' + view_type).children('option:selected'),
            view_id = selected_view.val(), shared = selected_view.data('shared');
        if (view_id === 'default') return err_notify($('#view_default_error__' + view_type).text());
        $.ajax({
            url: `/users/views/${view_id}/`,
            method: 'PATCH',
            data: {shared: !shared},
            success: function() {
                selected_view.data('shared', !shared);
                success_notify(
                    shared ?
                        $('#view_hidden_message__' + view_type).text() :
                        $('#view_shared_message__' + view_type).text()
                );
            }
        });
    });

    $('#view_prefer_btn__' + view_type).click(function () {
        let view_id = $('#view_list__' + view_type).val(), method, url;
        if (view_id === 'default') {
            method = 'DELETE';
            url = `/users/views/prefer-default/${view_type}/`;
        }
        else {
            method = 'POST';
            url = `/users/views/${view_id}/prefer/`;
        }
        $.ajax({
            url: url,
            method: method,
            // dataType: 'json',
            success: function() {
                success_notify($('#view_preferred_message__' + view_type).text());
            }
        });
    });

    $('#view_show_default_btn__' + view_type).click(function () {
        window.location.href = clear_query_params(window.location.href).slice(0, -1);
    });

    let show_viewform_btn = $('#view_show_form_btn_' + view_type);
    show_viewform_btn.popup();
    show_viewform_btn.click(function () {
        show_viewform_btn.popup('hide');
        let view_segment = $('#view_form_segment_' + view_type);
        view_segment.is(':visible') ? view_segment.hide() : view_segment.show();
        return false;
    });

    $('#view_add_column_btn_' + view_type).click(function () {
        let selected_column = $('#view_available_columns_' + view_type).children('option:selected');
        $('<option>', {
            value: selected_column.val(),
            text: selected_column.text(),
            title: selected_column.text()
        }).appendTo('#view_' + view_type + '__columns');
        return false;
    });

    $('#view_remove_column_btn_' + view_type).click(function () {
        $('#view_' + view_type + '__columns').children('option:selected').remove();
        return false;
    });

    $('#view_move_columns_up_' + view_type).click(function () {
        let $op = $('#view_' + view_type + '__columns').children('option:selected');
        if ($op.length) $op.first().prev().before($op);
    });

    $('#view_move_columns_down_' + view_type).click(function () {
        let $op = $('#view_' + view_type + '__columns').children('option:selected');
        if ($op.length) $op.last().next().after($op);
    });

    $('#order_by_attr__' + view_type).parent().checkbox({
        onChecked: function() { $('#order_attr_value_div__' + view_type).show() }
    });
    $('[id^="order_by_"]').each(function () {
        if ($(this).attr('id').startsWith('order_by_attr__') || $(this).attr('id').split('__')[1] !== view_type) {
            return true;
        }
        $(this).parent().checkbox({
            onChecked: function() {
                $('#order_attr_value_div__' + view_type).hide();
            }
        });
    });
};

window.update_colors = function (table) {
    if (!table.hasClass('alternate-color')) return false;
    let is_dark = false;
    table.find('tbody').first().find('tr:visible').each(function () {
        if (is_dark) {
            $(this).css('background', '#f0fcfe');
            is_dark = false;
        }
        else {
            $(this).css('background', 'white');
            is_dark = true;
        }
    });
    return true;
};

window.getFileExtension = function(name) {
    let found = name.lastIndexOf('.') + 1;
    return found > 0 ? name.substr(found) : '';
};

window.isFileReadable = function(name) {
    let readable_extensions = ['txt', 'json', 'xml', 'c', 'aspect', 'i', 'h', 'tmpl', 'python', 'yml'],
        extension = getFileExtension(name);
    return ($.inArray(extension, readable_extensions) !== -1 || name === 'README');
};

window.getUrlParameter = function (sParam) {
    let sPageURL = window.location.search.substring(1),
        sURLVariables = sPageURL.split('&'),
        sParameterName, i;

    for (i = 0; i < sURLVariables.length; i++) {
        sParameterName = sURLVariables[i].split('=');

        if (sParameterName[0] === sParam) {
            return sParameterName[1] === undefined ? true : decodeURIComponent(sParameterName[1]);
        }
    }
};

window.get_url_with_get_parameters = function (url, params) {
    let new_url = url;
    $.each(params, function (key, value) {
        if (new_url.indexOf(key + '=') > -1) {
            let url_regex = new RegExp('(' + key + "=).*?(&|$)");
            new_url = new_url.replace(url_regex, '$1' + value + '$2');
        }
        else if (new_url.indexOf('?') > -1) new_url += '&' + key + '=' + value;
        else new_url += '?' + key + '=' + value;
    });
    return new_url;
};

String.prototype.format = String.prototype.f = function(){
	let args = arguments;
	return this.replace(/{(\d+)}/g, function(m, n){
	    return args[n] ? args[n] : m
	});

};

window.activate_warn_modal = function (warn_modal_id, activator, error_text, on_confirm) {
    let modal_div = $('#' + warn_modal_id);
    if (!modal_div.length) return false;

    if (!error_text) error_text = 'Warning!';
    modal_div.find('.warn-text').text(error_text);

    let confirm_btn = modal_div.find('.modal-confirm'),
        cancel_btn = modal_div.find('.modal-cancel');
    modal_div.modal({closable: false, transition: 'fade in', autofocus: false});
    cancel_btn.click(function () {
        modal_div.modal('hide')
    });
    if (activator) {
        $(activator).click(function () {
            modal_div.modal('show')
        });
    }
    confirm_btn.click(function () {
        modal_div.modal('hide');
        if (on_confirm) on_confirm();
    });
    return modal_div;
};

window.update_action_button = function(btn_obj, disable=false) {
    if (disable) {
        if (!btn_obj.hasClass('disabled')) btn_obj.addClass('disabled');
    }
    else {
        if (btn_obj.hasClass('disabled')) btn_obj.removeClass('disabled');
    }
};

window.is_mac = function () {
    let userAgent = navigator.userAgent;
    let edge = /Edge\/(\d+)/.exec(userAgent)
    let ios = !edge && /AppleWebKit/.test(userAgent) && /Mobile\/\w+/.test(userAgent)
    return ios || /Mac/.test(navigator.platform)
}

$(document).ready(function () {
    $('.browse').popup({
        inline: true,
        hoverable: true,
        position: 'bottom left',
        lastResort: 'bottom left',
        delay: {
            show: 300,
            hide: 600
        }
    });
    $('.ui.checkbox').checkbox();
    $('.ui.accordion').accordion();
    // $('.note-popup').each(function () {
    //     let position = $(this).data('position');
    //     position ? $(this).popup({position: position}) : $(this).popup();
    // });
    $('.note-popup').popup();

    $('.ui.range').each(function () {
        let range_preview = $('#' + $(this).data('preview')),
            range_input = $('#' + $(this).data('input')),
            range_min = parseInt($(this).data('min')),
            range_max = parseInt($(this).data('max')),
            range_step = parseInt($(this).data('step')),
            range_start = parseInt(range_input.val());
        range_preview.text(range_start);
        $(this).range({
            min: range_min, max: range_max, step: range_step, start: range_start,
            onChange: function (value) {
                range_input.val(value);
                range_preview.text(value);
            }
        });
    });

    $('.page-link-icon').click(function () {
        window.location.replace(
            get_url_with_get_parameters(window.location.href, {'page': $(this).data('page-number')})
        );
    });

    $('.view-type-buttons').each(function () {
        set_actions_for_views($(this).val());
        return true;
    });

    //=============
    // Upload jobs
    let upload_jobs_modal = $('#upload_jobs_modal'),
        upload_jobs_modal_show = $(upload_jobs_modal.data('activator'));
    if (upload_jobs_modal_show.length && !upload_jobs_modal_show.hasClass('disabled')) {
        let upload_jobs_file_input = $('#upload_jobs_file');
        upload_jobs_modal.modal({transition: 'vertical flip'})
            .modal('attach events', upload_jobs_modal.data('activator'), 'show');

        upload_jobs_modal.find('.modal-cancel').click(function () {
            upload_jobs_modal.modal('hide')
        });

        upload_jobs_file_input.on('fileselect', function () {
            let files = $(this)[0].files,
                filename_list = $('<ul>');
            for (let i = 0; i < files.length; i++) filename_list.append($('<li>', {text: files[i].name}));
            $('#upload_jobs_filename').html(filename_list);
        });

        upload_jobs_modal.find('.modal-confirm').click(function () {
            let files = upload_jobs_file_input[0].files,
                data = new FormData();
            if (files.length <= 0) return err_notify($('#error__no_file_chosen').text());
            for (let i = 0; i < files.length; i++) data.append('file', files[i]);

            upload_jobs_modal.modal('hide');
            $('#dimmer_of_page').addClass('active');
            $.ajax({
                url: $(this).data('url'),
                type: 'POST',
                data: data,
                dataType: 'json',
                contentType: false,
                processData: false,
                mimeType: 'multipart/form-data',
                xhr: function() {
                    return $.ajaxSettings.xhr();
                },
                success: function () {
                    $('#dimmer_of_page').removeClass('active');
                    window.location.href = $('#uploading_status_link').attr('href');
                }
            });
            return false;
        });
    }

    //==============
    // Upload marks
    let upload_marks_modal = $('#upload_marks_modal'),
        upload_marks_modal_show = $(upload_marks_modal.data('activator'));
    if (upload_marks_modal_show.length && !upload_marks_modal_show.hasClass('disabled')) {
        upload_marks_modal.modal('setting', 'transition', 'vertical flip')
            .modal('attach events', upload_marks_modal.data('activator'), 'show');

        $('#upload_marks_file').on('fileselect', function () {
            let files = $(this)[0].files,
                filename_list = $('<ul>');
            for (let i = 0; i < files.length; i++) filename_list.append($('<li>', {text: files[i].name}));
            $('#upload_marks_filename').html(filename_list);
        });

        upload_marks_modal.find('.modal-cancel').click(function () {
            upload_marks_modal.modal('hide')
        });

        upload_marks_modal.find('.modal-confirm').click(function () {
            let files = $('#upload_marks_file')[0].files,
                data = new FormData();
            if (files.length <= 0) return err_notify($('#error__no_file_chosen').text());
            for (let i = 0; i < files.length; i++) data.append('file', files[i]);

            upload_marks_modal.modal('hide');
            $('#dimmer_of_page').addClass('active');
            $.ajax({
                url: $(this).data('url'),
                type: 'POST',
                data: data,
                dataType: 'json',
                contentType: false,
                processData: false,
                mimeType: 'multipart/form-data',
                xhr: function() { return $.ajaxSettings.xhr() },
                success: function (resp) {
                    $('#dimmer_of_page').removeClass('active');
                    if ('url' in resp) window.location.href = resp['url'];
                    else success_notify(resp['message']);
                }
            });
        });
    }
    $('.alternate-color').each(function () {
        update_colors($(this))
    });

    // Activate file content modal with ability to download it
    let file_content_modal = $('#file_content_modal');
    file_content_modal.modal({transition: 'fade'});
    $('.file-content-activator').click(function (event) {
        event.preventDefault();
        let download_url = $(this).data('download');
        $.get($(this).data('url'), {}, function (resp) {
            file_content_modal.find('.filecontent').text(resp);
            if (download_url) file_content_modal.find('.download-url').attr('href', download_url).show();
            else file_content_modal.find('.download-url').hide();
            file_content_modal.modal('show');
        });
    });
    file_content_modal.find('.modal-cancel').click(function () {
        file_content_modal.modal('hide');
        file_content_modal.find('.filecontent').empty();
        file_content_modal.find('.download-url').attr('href', '#');
    })
});
