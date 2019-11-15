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

$(document).ready(function () {
    $('.bottom-attached').parent().addClass('with-bottom-attachment');

    $('.parent-popup').popup({inline:true});
    $('.ui.dropdown').dropdown();

    $('.mark-inline-form').click(function () {
        get_inline_mark_form($(this).data('url'), $('#inline_mark_form'));
    });

    $('#show_leaf_attributes').click(function () {
        let attr_table = $('#leaf_attributes');
        attr_table.is(':hidden') ? attr_table.show() : attr_table.hide();
    });

    $('.confirm-mark-btn').click(function () {
        $.ajax({
            url: $(this).data('url'), method: $(this).data('method'),
            success: function () { window.location.replace('') }
        })
    });
    $('.like-mark-btn').click(function () {
        $.ajax({
            url: $(this).data('url'), method: $(this).data('method'),
            success: function () { window.location.replace('') }
        })
    });

    $('.like-popup').each(function () {
        let popup_id = $(this).data('popupid');
        if (!popup_id) return;
        $(this).popup({
            hoverable: true,
            popup: popup_id,
            position: 'top left',
            lastResort: 'bottom left',
            target: $(this).parent().find('button').last(),
            offset: -30,
            delay: {show: 100, hide: 300}
        });
    });
    $('.dislike-popup').each(function () {
        let popup_id = $(this).data('popupid');
        if (!popup_id) return;
        $(this).popup({
            hoverable: true,
            popup: popup_id,
            position: 'top left',
            lastResort: 'bottom left',
            delay: {show: 100, hide: 300}
        });
    });

});