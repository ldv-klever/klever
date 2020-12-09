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

window.get_tags_values = function () {
    let selected_tags = [];
    $('#selected_tags').children('span').each(function () {
        selected_tags.push($(this).text());
    });
    return selected_tags;
};

window.activate_tags = function () {
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
            delay: {show: 100, hide: 300},
            position: 'top left',
            exclusive: true,
            variation: 'very wide'
        })
    });

    function update_tags(deleted, added) {
        $.ajax({
            url: '/marks/api/tags-data/' + $('#tags_type').val() + '/',
            type: 'GET',
            traditional: true,
            data: {
                selected: get_tags_values(),
                deleted: deleted,
                added: added
            },
            success: function (resp) {
                $('#mark_tags_container').html(resp);
                activate_tags();
            }
        });
    }

    $('#tag_list').dropdown({
        useLabels: false,
        className: {
            label: 'ui label ' + $('#tag_label_color').text()
        },
        message: {
            noResults: $('#error__no_results').text(),
            count: ''
        },
        onChange: function () {
            $(this).dropdown('hide');
            update_tags(null, $('#tag_list').val());
        }
    });
    $('.remove-mark-tag').click(function () {
        update_tags($(this).data('tag'));
    });
};
