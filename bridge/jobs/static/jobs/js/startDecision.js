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

function StartDecision(conf_url, values_url) {
    this.conf_url = conf_url;
    this.values_url = values_url;
    return this;
}

StartDecision.prototype.onSelectionChanged = function (new_value) {
    const $this = this;

    let file_form = $('#upload_file_conf_form'),
        lastconf_form = $('#select_lastconf_form');
    if (new_value === 'file_conf') {
        lastconf_form.hide();
        file_form.show();
    }
    else if(new_value === 'lastconf') {
        file_form.hide();
        $.post($this.conf_url, {decision: parseInt($('#lastconf_select').val())}, function (resp) {
            $this.update(resp)
        });
        lastconf_form.show();
    }
    else {
        file_form.hide();
        lastconf_form.hide();
        $.post($this.conf_url, {conf_name: new_value}, function (resp) {
            $this.update(resp)
        });
    }
};

StartDecision.prototype.initialize = function() {
    const $this = this;
    $('.normal-dropdown').dropdown();

    $('#configuration_mode').dropdown({
        onChange: function (value) {
            $this.onSelectionChanged(value);
        }
    });
    $('#file_conf').on('fileselect', function () {
        let data = new FormData();
        data.append('file_conf', $(this)[0].files[0]);
        api_upload_file($this.conf_url, 'POST', data, function (resp) {
            $this.update(resp);
            $('#dimmer_of_page').removeClass('active');
        });
    });
    $('#lastconf_select').dropdown({
        onChange: function () {
            $.post($this.conf_url, {decision: parseInt($('#lastconf_select').val())}, function (resp) {
                $this.update(resp)
            });
        }
    });

    $('.get-attr-value').click(function () {
        $.ajax({
            url: $this.values_url,
            type: 'POST',
            data: {
                name: $(this).data('name'),
                value: $(this).data('value')
            },
            success: function (resp) {
                Object.keys(resp).forEach(function(key) {
                    $('#' + key).val(resp[key])
                });
            }
        });
    });
};

StartDecision.prototype.update = function(resp) {
    $(`input[name="priority"][value="${resp['priority']}"]`).prop('checked', true);
    $(`input[name="scheduler"][value="${resp['scheduler']}"]`).prop('checked', true);
    $(`input[name="weight"][value="${resp['weight']}"]`).prop('checked', true);
    $(`input[name="coverage_details"][value="${resp['coverage_details']}"]`).prop('checked', true);
    $('#max_tasks').val(resp['max_tasks']);
    $('#parallelism_0').val(resp['parallelism'][0]);
    $('#parallelism_1').val(resp['parallelism'][1]);
    $('#parallelism_2').val(resp['parallelism'][2]);
    $('#parallelism_3').val(resp['parallelism'][3]);
    $('#parallelism_4').val(resp['parallelism'][4]);
    $('#memory').val(resp['memory']);
    $('#cpu_num').val(resp['cpu_num'] || '');
    $('#disk_size').val(resp['disk_size']);
    $('#cpu_model').val(resp['cpu_model']);
    $('#cpu_time_exec_cmds').val(resp['cpu_time_exec_cmds']);
    $('#memory_exec_cmds').val(resp['memory_exec_cmds']);
    $('#cpu_time_exec_emg').val(resp['cpu_time_exec_emg']);
    $('#memory_exec_emg').val(resp['memory_exec_emg']);
    $('#console_level').dropdown('set selected', resp['console_level']);
    $('#file_level').dropdown('set selected', resp['file_level']);
    $('#console_formatter').val(resp['console_formatter']);
    $('#file_formatter').val(resp['file_formatter']);
    $('.boolean-value').each(function () {
        if (resp[$(this).attr('id')]) $(this).prop('checked', true);
        else $(this).prop('checked', false);
    });
};

StartDecision.prototype.serialize = function() {
    let data = {
            priority: $('input[name="priority"]:checked').val(),
            scheduler: $('input[name="scheduler"]:checked').val(),
            weight: $('input[name="weight"]:checked').val(),
            coverage_details: $('input[name="coverage_details"]:checked').val(),
            max_tasks: $('#max_tasks').val(),
            parallelism: [$('#parallelism_0').val(), $('#parallelism_1').val(), $('#parallelism_2').val(), $('#parallelism_3').val(), $('#parallelism_4').val()],
            memory: $('#memory').val().replace(/,/, '.'),
            cpu_num: $('#cpu_num').val() || null,
            disk_size: $('#disk_size').val().replace(/,/, '.'),
            cpu_model: $('#cpu_model').val(),
            cpu_time_exec_cmds: $('#cpu_time_exec_cmds').val().replace(/,/, '.'),
            memory_exec_cmds: $('#memory_exec_cmds').val().replace(/,/, '.'),
            cpu_time_exec_emg: $('#cpu_time_exec_emg').val().replace(/,/, '.'),
            memory_exec_emg: $('#memory_exec_emg').val().replace(/,/, '.'),
            console_level: $('#console_level').val(),
            file_level: $('#file_level').val(),
            console_formatter: $('#console_formatter').val(),
            file_formatter: $('#file_formatter').val()
        };
        $('.boolean-value').each(function () {
            data[$(this).attr('id')] = $(this).is(':checked');
        });

        return JSON.stringify(data);
};

StartDecision.prototype.initialize_sch_user_modal = function(add_user_url) {
    let scheduler_user_modal = $('#scheduler_user_modal'),
        login_input = scheduler_user_modal.find('#sch_login'),
        passwd_input = scheduler_user_modal.find('#sch_password'),
        passwd_retype_input = scheduler_user_modal.find('#sch_password_retype');

    if (!scheduler_user_modal.length) return false;
    scheduler_user_modal.modal({transition: 'fade', closable: false});
    scheduler_user_modal.find('.warn-popup').popup();

    login_input.on('input', this.check_sch_user_data);
    passwd_input.on('input', this.check_sch_user_data);
    passwd_retype_input.on('input', this.check_sch_user_data);

    scheduler_user_modal.find('.modal-confirm').click(function () {
        $.ajax({url: add_user_url, type: 'POST', data: {
            login: login_input.val(),
            password: passwd_input.val()
        }, success: function () {
            success_notify($('#verifiercloud_cred_saved').text(), 10000);
            scheduler_user_modal.modal('hide');
            $('.scheduler-checkbox').checkbox({onChecked: function(){}});
        }});
    });

    scheduler_user_modal.find('.modal-cancel').click(function () {
        scheduler_user_modal.modal('hide')
    });

    // Initialize checkbox
    $('.scheduler-checkbox').checkbox({onChecked: function () {
        if ($(this).val() === 'VerifierCloud') scheduler_user_modal.modal('show');
    }});
};

StartDecision.prototype.check_sch_user_data = function() {
    let err_found = false,
        scheduler_user_modal = $('#scheduler_user_modal'),
        login_input = scheduler_user_modal.find('#sch_login'),
        passwd_input = scheduler_user_modal.find('#sch_password'),
        passwd_retype_input = scheduler_user_modal.find('#sch_password_retype'),
        confirm_btn = scheduler_user_modal.find('.modal-confirm');

    if (login_input.val().length === 0) {
        err_found = true;
        $('#sch_login_required').show();
        login_input.parent().addClass('error');
    }
    else {
        $('#sch_login_required').hide();
        login_input.parent().removeClass('error');
    }

    if (passwd_input.val().length === 0) {
        err_found = true;
        $('#sch_password_required').show();
        passwd_input.parent().addClass('error');
    }
    else {
        $('#sch_password_required').hide();
        passwd_input.parent().removeClass('error');
    }

    if (passwd_retype_input.val().length === 0) {
        err_found = true;
        $('#sch_password_retype_required').show();
        passwd_retype_input.parent().addClass('error');
    }
    else {
        $('#sch_password_retype_required').hide();
        passwd_retype_input.parent().removeClass('error');
    }

    if (passwd_input.val().length && passwd_retype_input.val().length && passwd_retype_input.val() !== passwd_input.val()) {
        err_found = true;
        $('#sch_password_retype_match').show();
        passwd_retype_input.parent().addClass('error');
    }
    else {
        $('#sch_password_retype_match').hide();
        passwd_retype_input.parent().removeClass('error');
    }

    if (err_found) {
        if (!confirm_btn.hasClass('disabled')) confirm_btn.addClass('disabled');
    }
    else confirm_btn.removeClass('disabled');

    return err_found;
};


StartDecision.prototype.selectDefaultOption = function () {
    const configuration_mode_select = $('#configuration_mode');
    if (configuration_mode_select.dropdown('get value') !== 'default') {
        // Don't call this.onSelectionChanged() as default options are already set
        configuration_mode_select.find('input').val('default');
        configuration_mode_select.dropdown('set selected', 'default');
    }
};
