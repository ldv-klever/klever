/*
 * Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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

function remove_user_role_form(id) {
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

function add_user_role() {
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
}

window.init_roles_form = function (user_roles_form_id, job_id, version) {
    $.get('/jobs/get_version_roles/' + job_id + '/' + version + '/', {}, function (resp) {
        if (resp.error) {
            err_notify(resp.error);
            return false;
        }
        $(user_roles_form_id).html(resp);
        var global_role_selector = $('#job_global_roles'), available_users = $('#job_available_users');

        global_role_selector.dropdown();
        available_users.dropdown();
        check_add_user_role();
        check_all_roles();

        $('#add_user_for_role').unbind().click(add_user_role);

        $("button[id^='remove_user_role__']").unbind().click(function () {
            var id = $(this).attr('id').replace('remove_user_role__', '');
            remove_user_role_form(id);
            check_add_user_role();
        });

        global_role_selector.unbind().change(function() {
            $('#all_user_roles').find("div[id^='job_user_role__']").each(function () {
                var id = $(this).attr('id').replace('job_user_role__', '');
                remove_user_role_form(id);
            });
            check_add_user_role();
            check_all_roles();
        });
    });
};

window.get_user_roles = function () {
    var user_roles = [];
    $('#all_user_roles').find("select[id^='job_user_role_select__']").each(function () {
        var user_id = $(this).attr('id').replace('job_user_role_select__', ''),
            user_role = $(this).children('option:selected').val();
        user_roles.push({user: user_id, role: user_role});
    });
    return JSON.stringify(user_roles);
};

window.global_role = function () { return $('#job_global_roles').children('option:selected').val() };