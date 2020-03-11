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

function UserRoleForm(form_id) {
    this.form_obj = $('#' + form_id);
    this.global_role_select = this.form_obj.find('#global_role_select').first();
    this.user_select_div = this.form_obj.find('#user_select_div').first();
    this.user_select = this.form_obj.find('#user_select').first();
    this.users_roles_div = this.form_obj.find('#users_roles_div').first();
    this.template_user_role = this.form_obj.find('#template__user_role').first();
    this.add_user_for_role = this.form_obj.find('#add_user_for_role').first();
    this.names = {};
    return this;
}

UserRoleForm.prototype.check_users_length = function() {
    this.user_select.children().length ? this.user_select_div.show() : this.user_select_div.hide();
};

UserRoleForm.prototype.remove_user_role = function(user_id) {
    this.user_select.append($('<option>', {value: user_id, text: this.names[user_id + '']}));
    this.form_obj.find('#user_role__' + user_id).remove();
};

UserRoleForm.prototype.global_role = function() {
    return this.global_role_select.children('option:selected').val();
};

UserRoleForm.prototype.add_user_role = function(user_id, user_name, selected_value) {
    let tmp_div = $('<div>', {id: 'user_role__' + user_id, class: 'ui grid segment'})
        .append(this.template_user_role.html());

    tmp_div.find("[for=user_role_select__]").each(function () {
        $(this).attr('for', $(this).attr('for') + user_id);
        $(this).text(user_name);
    });

    tmp_div.find("[id]").each(function () {
        $(this).attr('id', $(this).attr('id') + user_id);
    });
    tmp_div.find("select[id^='user_role_select__']").attr('class', 'ui dropdown');

    // Add action on "delete" button click
    let instance = this;
    tmp_div.find("#user_role_remove__" + user_id).click(function () {
        instance.remove_user_role(user_id);
        instance.check_users_length();
    });

    // Disable unavailable options and select first found one
    let has_selected = false,
        global_role = parseInt(this.global_role()),
        new_selector = tmp_div.find('#user_role_select__' + user_id);
    new_selector.children('option').each(function () {
        let option_value = parseInt($(this).val());
        if (option_value <= global_role) {
            // Disable option
            $(this).attr('disabled', 'disabled');
        }
        else if (!has_selected) {
            // Select first found active option or with provided value
            if (!selected_value || selected_value && parseInt(selected_value) === option_value) {
                $(this).attr('selected', 'selected');
                has_selected = true;
            }

        }
    });
    new_selector.dropdown();

    this.users_roles_div.append(tmp_div);
    this.names[user_id + ''] = user_name;
};

UserRoleForm.prototype.initialize = function (data) {
    let instance = this;

    // Set global role
    instance.global_role_select.dropdown('set selected', data['global_role']);
    instance.global_role_select.unbind().change(function () {
        instance.users_roles_div.find("div[id^='user_role__']").each(function () {
            instance.remove_user_role($(this).attr('id').replace('user_role__', ''));
        });

        // If global role is JOB_ROLE[4][0], then nothing to set for users, otherwise show users
        instance.global_role() === '4' ? instance.user_select_div.hide() : instance.check_users_length();
    });

    // Update available users list
    instance.user_select.empty();
    $.each(data['available_users'], function (i, user_data) {
        instance.user_select.append($('<option>', {'value': user_data['id'], 'text': user_data['name']}));
    });
    if (data['available_users'].length) instance.user_select.dropdown('set selected', data['available_users'][0]['id']);
    instance.check_users_length();
    instance.user_select.dropdown('refresh');

    // Create user roles segments
    instance.users_roles_div.empty();
    $.each(data['user_roles'], function (i, user_data) {
        instance.add_user_role(
            user_data['user'] + '',
            user_data['name'],
            user_data['role']
        )
    });

    // Action on "Add" button click
    instance.add_user_for_role.unbind().click(function () {
        let selected_user = instance.user_select.children('option:selected');
        instance.add_user_role(selected_user.val(), selected_user.text());
        selected_user.remove();
        instance.check_users_length();
        instance.user_select.dropdown('set selected', instance.user_select.children().first().val());
        instance.user_select.dropdown('refresh');
    });
};

UserRoleForm.prototype.get_roles = function () {
    let user_roles = [];
    this.users_roles_div.find('div[id^=user_role__]').each(function () {
        let user_id = $(this).attr('id').replace('user_role__', ''),
            role = $(this).find('#user_role_select__'  + user_id).first().children('option:selected').val();
        user_roles.push({'user': user_id, 'role': role});
    });
    return user_roles;
};
