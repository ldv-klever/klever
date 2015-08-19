
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

// For making safe post requests
$.ajaxSetup({
    beforeSend: function(xhr, settings) {
        if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
            var csrftoken = getCookie('csrftoken');
            xhr.setRequestHeader("X-CSRFToken", csrftoken);
        }
    }
});

$.extend({
    redirectPost: function (location, args) {
        var form = '<input type="hidden" name="csrfmiddlewaretoken" value="' + getCookie('csrftoken') + '">';
        $.each(args, function (key, value) {
            // value = value.split('"').join('\"');
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
    if (isNaN(duration)) {
        duration = 2500;
    }
    $.notify(message, {
        autoHide: true,
        autoHideDelay: duration,
        style: 'bootstrap',
        className: 'error'
    });
};

window.success_notify = function (message) {
    $.notify(message, {
        autoHide: true,
        autoHideDelay: 2500,
        style: 'bootstrap',
        className: 'success'
    });
};

window.download_job = function(job_id) {
    var interval = null;
    var try_lock = function() {
        $.ajax({
            url: job_ajax_url + 'downloadlock/',
            type: 'GET',
            dataType: 'json',
            async: false,
            success: function (resp) {
                if (resp.status) {
                    clearInterval(interval);
                    $('body').removeClass("loading");
                    window.location.replace(job_ajax_url + 'downloadjob/' + job_id + '/' + '?hashsum=' + resp.hash_sum);
                }
                else {
                    $('body').addClass("loading");
                }
            }
        });
    };
    $('body').addClass("loading");
    interval = setInterval(try_lock, 1000);
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
                if (data.status) {
                    var request_data = collect_data();
                    request_data['title'] = view_title;
                    request_data['view_type'] = filter_type;
                    $.ajax({
                        method: 'post',
                        url: job_ajax_url + 'save_view/',
                        dataType: 'json',
                        data: request_data,
                        success: function(save_data) {
                            if (save_data.status === 0) {
                                if (save_data.hasOwnProperty('view_name')) {
                                    $('#' + filter_type + '__available_views').append($('<option>', {
                                        text: save_data['view_name'],
                                        value: save_data['view_id']
                                    }));
                                    $('#' + filter_type + '__view_name_input').val('');
                                    success_notify(save_data.message);
                                }
                            }
                            else {
                                err_notify(data.message);
                            }
                        }
                    });
                }
                else {
                    err_notify(data.message);
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
                save_data.status === 0 ? success_notify(save_data.message) : err_notify(save_data.message);
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
                if (data.status === 0) {
                    $('#' + filter_type + '__available_views').children('option:selected').remove();
                    success_notify(data.message)
                }
                else {
                    err_notify(data.message)
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
                data.status === 0 ? success_notify(data.message) : err_notify(data.message);
            }
        });
    });
};
