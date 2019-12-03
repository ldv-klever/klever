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

function SourceProcessor(container, title_container, history_container, data_container, legend_container) {
    this.container = $(container);
    this.title_container = $(title_container);
    this.history = $(history_container);
    this.data_container = $(data_container);
    this.legend_container = $(legend_container);
    this.ref_click_callback = null;
    this.source_references = '#source_references_links';
    this.source_declarations = '#source_declarations_popup';
    this.url = null;
    this.cov_data_url = null;
    this.errors = {
        line_not_found: 'Line not found'
    };
    this.selected_line = null;
    return this;
}

SourceProcessor.prototype.initialize = function(ref_click_callback, source_url) {
    let instance = this;

    instance.ref_click_callback = ref_click_callback;
    instance.url = source_url;

    window.addEventListener('popstate', function(e) {
        let new_state = e.state;
        new_state ? instance.get_source(new_state[1], new_state[0], false) : history.back();
    });

    let source_container = this.container,
        source_window = source_container.parent();

    source_window.on('scroll', function () {
        $(this).find('.SrcLine').css('left', $(this).scrollLeft());
    });
    source_container.on('mouseenter', '.SrcLineCov[data-value]', function () {
        $(this).append($('<span>', {'class': 'SrcNumberPopup', text: $(this).data('value')}));
    });
    source_container.on('mouseleave', '.SrcLineCov[data-value]', function () {
        $(this).find('.SrcNumberPopup').remove();
    });
    source_container.on('mouseenter', '.SrcFuncCov[data-value]', function () {
        $(this).append($('<span>', {'class': 'SrcNumberPopup', text: $(this).data('value')}));
    });
    source_container.on('mouseleave', '.SrcFuncCov[data-value]', function () {
        $(this).find('.SrcNumberPopup').remove();
    });
    source_container.on('mouseenter', '.SrcCode[data-value]', function () {
        $(this).siblings('.SrcLine').find('.SrcLineCov')
            .append($('<span>', {'class': 'SrcNumberPopup', text: $(this).data('value')}));
    });
    source_container.on('mouseleave', '.SrcCode[data-value]', function () {
        $(this).siblings('.SrcLine').find('.SrcNumberPopup').remove();
    });
};

SourceProcessor.prototype.init_references = function(ref_id, ref_popup) {
    let instance = this,
        data_html = instance.container.find('#' + ref_id).html();
    ref_popup.find('.ReferencesContainer').html(data_html);
    ref_popup.find('.SrcRefLink').click(function () {
        if (instance.ref_click_callback) instance.ref_click_callback();
        instance.get_source($(this).data('line'), $(this).parent().data('file'));
    })
};

SourceProcessor.prototype.refresh = function() {
    let instance = this,
        source_references_div = instance.container.find(this.source_references),
        source_declarations_popup = instance.container.find(this.source_declarations);

    let cov_data_url = this.container.find('#coverage_data_url');
    instance.cov_data_url = cov_data_url.length ? cov_data_url.val() : null;

    this.container.find('.SrcRefToLink').click(function () {
        if (instance.ref_click_callback) instance.ref_click_callback();

        let file_index = $(this).data('file'), file_name;
        if (file_index === null) file_name = instance.title_container.text();
        else file_name = instance.container.find(`.SrcFileData[data-index="${file_index}"]`).text();

        instance.get_source(parseInt($(this).data('line')), file_name);
    });

    this.container.find('.SrcRefToDeclLink').popup({
        popup: this.source_declarations,
        onShow: function (activator) {
            instance.init_references($(activator).data('declaration'), source_declarations_popup)
        },
        position: 'bottom left',
        lastResort: 'bottom left',
        hoverable: true,
        inline: true,
        delay: {
            show: 100,
            hide: 300
        }
    });

    this.container.find('.SrcRefFromLink').popup({
        popup: this.source_references,
        onShow: function (activator) {
            instance.init_references($(activator).data('id'), source_references_div)
        },
        position: 'bottom left',
        lastResort: 'bottom left',
        hoverable: true,
        inline: true,
        delay: {
            show: 100,
            hide: 300
        }
    });
    this.container.find('.SrcCovDataLink').click(function () {
        let selected_src_line = $(this).parent();

        if (!instance.data_container || !instance.cov_data_url) return false;

        let filename = instance.title_container.text(), line = $(this).text();
        instance.unselect_line();
        $.ajax({
            url: instance.cov_data_url,
            type: 'GET',
            data: {file_name: encodeURIComponent(filename), line: line},
            success: function (resp) {
                instance.select_span(selected_src_line.parent());
                instance.data_container.html(resp);
                instance.data_container.find('.CoverageDataName').click(function () {
                    if ($(this).hasClass('CoverageDataNameSelected')) return;
                    instance.data_container.find('.CoverageDataNameSelected').removeClass('CoverageDataNameSelected');
                    instance.data_container.find('.CoverageDataValue').hide();
                    instance.data_container.find(`.CoverageDataValue[data-name="${$(this).text()}"]`).show();
                    $(this).addClass('CoverageDataNameSelected');
                });
                instance.data_container.find('.CoverageDataName').first().click();
            }
        }).fail(function (jqXHR, textStatus, text) {
            instance.data_container.html(text);
        });
    });
    if (instance.legend_container.length) {
        let src_legend = instance.container.find('#source_legend');
        if (src_legend.length) instance.legend_container.html(src_legend.html());
    }
};

SourceProcessor.prototype.unselect_line = function() {
    if (this.selected_line) {
        this.selected_line.removeClass('SrcLineSelected');
        this.selected_line = null;
    }
};

SourceProcessor.prototype.select_span = function(src_line) {
    this.unselect_line();

    if (src_line.length) {
        let source_window = this.container.parent(),
            cov_line_obj = src_line.find('.SrcLineCov');
        source_window.scrollTop(src_line.position().top - source_window.height() * 3/10);
        cov_line_obj.addClass('SrcLineSelected');
        this.selected_line = cov_line_obj;
    }
    else err_notify(this.errors.line_not_found);
};

SourceProcessor.prototype.select_line = function(line) {
    this.select_span(this.container.find(`#SrcL_${line}`));
};

SourceProcessor.prototype.get_source = function(line, filename, save_history=true) {
    let instance = this;
    if (save_history){
        let state_url = get_url_with_get_parameters(window.location.href, {
            'source': encodeURIComponent(filename), 'sourceline': line
        });
        history.pushState([filename, line], null, state_url);
    }

    if (filename === this.title_container.text()) instance.select_line(line);
    else {
        $.ajax({
            url: instance.url,
            type: 'GET',
            data: {
                file_name: encodeURIComponent(filename),
                with_legend: !!instance.legend_container.length
            },
            success: function (resp) {
                instance.container.html(resp);
                instance.selected_line = null;
                instance.title_container.text(filename);
                instance.title_container.popup({content: filename});
                instance.select_line(line);
                instance.refresh();
            }
        });
    }
};
