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


class CoverageProcessor {
    _coveredFunctions;
    _uncoveredFunctions;
    _sortedCoveredFunctions;
    _mostCoveredLines;
    _mostGlobalCoveredLines;

    constructor(sourceProcessor, dataWindowSelector, statTableSelector, onSelectionChange) {
        this.sourceProcessor = sourceProcessor;
        this.sourceContainer = sourceProcessor.container;
        this.dataWindow = $(dataWindowSelector);
        this.statTable = $(statTableSelector).find('table').first();
        this.onSelectionChange = onSelectionChange;
        this.initialFile = this.currentFile;
        this._initStatisticsTable();
        this._initCodeNavigation();
    }

    openFirstFile() {
        // Open directories to first found file
        this.statTable.find('tbody').children('tr').each(function () {
            let expander_link = $(this).find('.tg-expander');
            if (expander_link.length) {
                expander_link.click();
                return true;
            }
            return false;
        });

        // Open file from url or first found file in coverage table
        let fileName = getUrlParameter('source'), fileLine = getUrlParameter('sourceline');
        if (fileName) {
            this.sourceProcessor.get_source(fileLine, fileName, false);
            history.replaceState([fileName, fileLine], null, window.location.href);
        }
        else this.statTable.find('.tree-file-link:visible').first().click();
    }

    _initStatisticsTable() {
        let $this = this;

        // Activate expand/collapse tree actions
        $this.statTable.find('.tg-expander').click(function (event) {
            let node = $(this).closest('tr');
            if (node.hasClass('tg-expanded')) {
                $this._collapseStatTree(node);
            } else {
                $this._expandStatTree(node, event.shiftKey);
            }
            update_colors($this.statTable);
        });

        // Activate opening new source file
        $this.statTable.find('.tree-file-link').click(function (event) {
            event.preventDefault();
            $this.dataWindow.empty();
            $this.onSelectionChange?.();
            $this.sourceProcessor.get_source(1, $(this).data('path'));
        });

        update_colors($this.statTable);
    }

    _initCodeNavigation() {
        // Function/lines coverage navigation buttons

        $('#next_cov_btn').click(() => {
            this._changeSelection(this.coveredFunctions, 1, 'SrcFuncCov');
        });

        $('#prev_cov_btn').click(() => {
            this._changeSelection(this.coveredFunctions, -1, 'SrcFuncCov');
        });

        $('#next_uncov_btn').click(() => {
            this._changeSelection(this.uncoveredFunctions, 1, 'SrcFuncCov');
        });

        $('#prev_uncov_btn').click(() => {
            this._changeSelection(this.uncoveredFunctions, -1, 'SrcFuncCov');
        });

        $('#next_srt_btn').click(() => {
            this._changeSelection(this.sortedCoveredFunctions, 1, 'SrcFuncCov');
        });

        $('#prev_srt_btn').click(() => {
            this._changeSelection(this.sortedCoveredFunctions, -1, 'SrcFuncCov');
        });

        $('#next_mostcov_btn').click(() => {
            this._changeSelection(this.mostCoveredLines, 1, 'SrcLineCov');
        });

        $('#prev_mostcov_btn').click(() => {
            this._changeSelection(this.mostCoveredLines, -1, 'SrcLineCov');
        });

        $('#next_global_mostcov_btn').click(() => {
            this._changeGlobalSelection(this.mostGlobalCoveredLines, 1);
        });

        $('#prev_global_mostcov_btn').click(() => {
            this._changeGlobalSelection(this.mostGlobalCoveredLines, -1);
        });
    }

    get coveredFunctions() {
        if (this.currentFile !== this.initialFile) {
            this._clearCache();
        }
        if (!this._coveredFunctions) {
            this._coveredFunctions = this.sourceContainer.find('.SrcFuncCov[data-value]').filter(function() {
                return $(this).data('value') > 0
            });
        }
        return this._coveredFunctions;
    }

    get uncoveredFunctions() {
        if (this.currentFile !== this.initialFile) {
            this._clearCache();
        }
        if (!this._uncoveredFunctions) {
            this._uncoveredFunctions = this.sourceContainer.find('.SrcFuncCov[data-value]').filter(function() {
                return $(this).data('value') === 0
            });
        }
        return this._uncoveredFunctions;
    }

    get sortedCoveredFunctions() {
        if (this.currentFile !== this.initialFile) {
            this._clearCache();
        }
        if (!this._sortedCoveredFunctions) {
            // Sort elements in descending order
            this._sortedCoveredFunctions = this.coveredFunctions.sort(function(a, b) {
                let n1 = $(a).data('value'), n2 = $(b).data('value');
                return (n1 > n2) ? -1 : (n1 < n2) ? 1 : 0;
            });
        }
        return this._sortedCoveredFunctions;
    }

    get mostCoveredLines() {
        if (this.currentFile !== this.initialFile) {
            this._clearCache();
        }
        if (!this._mostCoveredLines) {
            this._mostCoveredLines = this.sourceContainer.find('.SrcLineCov[data-value]').filter(function() {
                return $(this).data('value') > 0
            }).sort(function(a, b) {
                let n1 = $(a).data('value'), n2 = $(b).data('value');
                return (n1 > n2) ? -1 : (n1 < n2) ? 1 : 0;
            }).slice(0, 30);
        }
        return this._mostCoveredLines;
    }

    get mostGlobalCoveredLines() {
        if (!this._mostGlobalCoveredLines) {
            let mostCoveredLinesStatisticsContainer = $('#most_global_covered_lines');
            let statistics = [];
            if (mostCoveredLinesStatisticsContainer.length) {
                mostCoveredLinesStatisticsContainer.children('span').each(function() {
                    statistics.push($(this).text());
                })
            }
            this._mostGlobalCoveredLines = statistics;
        }
        return this._mostGlobalCoveredLines;
    }

    _expandStatTree(node, chain) {
        let $this = this,
            nodeID = node.data('tg-id'),
            nodeChildren = node.nextAll(`tr[data-tg-parent="${nodeID}"]`);

        // Show all children
        nodeChildren.show();

        // Change node icon (closed folder to open)
        node.find('.tg-expander').addClass('open');

        // Add "expanded" flag
        node.addClass('tg-expanded');

        // Expand children in case of shiftKey event (chain is true)
        if (chain) {
            nodeChildren.filter(function() {
                return !$(this).hasClass('tg-leaf');
            }).each(function() {
                $this._expandStatTree($(this), chain);
            });
        }
    }

    _collapseStatTree(node) {
        let $this = this,
            nodeID = node.data('tg-id'),
            nodeChildren = node.nextAll(`tr[data-tg-parent="${nodeID}"]`);

        // Collapse expanded children
        nodeChildren.filter(function() {
            return $(this).hasClass('tg-expanded');
        }).each(function() {
            $this._collapseStatTree($(this));
        });

        // Hide all children
        nodeChildren.hide();

        // Change node icon (open folder to closed)
        node.find('.tg-expander').removeClass('open');

        // Clear "expanded" flag
        node.removeClass('tg-expanded');
    }

    static _getNewIndex(currentIndex, listSize, change) {
        if (currentIndex < 0) {
            // If no elements from the list is selected then
            // go to first element if we are moving forward or last one otherwise
            return change > 0 ? 0 : listSize - 1;
        }
        currentIndex += change;
        return currentIndex < 0 ? listSize - 1 : currentIndex < listSize ? currentIndex : 0;
    }

    _changeSelection(linesCollection, change, covTypeClass) {
        this.dataWindow.empty();
        this.onSelectionChange?.();

        // Do nothing if lines collection is empty
        if (!linesCollection.length) {
            return;
        }

        let ind = 0;

        // Get selected line and increase index in a list
        let selectedLine = this.sourceProcessor.selected_line?.parent().find(`.${covTypeClass}:first`);
        if (selectedLine && selectedLine.length) {
            ind = CoverageProcessor._getNewIndex(linesCollection.index(selectedLine), linesCollection.length, change);
        }

        // Select new line
        this.sourceProcessor.select_span($(linesCollection.get(ind)).parent());
    }

    _changeGlobalSelection(linesCollection, change) {
        this.dataWindow.empty();
        this.onSelectionChange?.();

        // Do nothing if lines collection is empty
        if (!linesCollection.length) {
            return;
        }

        let ind = 0;

        // Get selected line and change index in a list
        let currentFile = null;
        if (this.sourceProcessor.selected_line) {
            let currentLine = this.sourceProcessor.selected_line.parent().attr('id').replace( /^\D+/g, '');
            currentFile = this.sourceProcessor.title_container.text();
            ind = CoverageProcessor._getNewIndex(
                linesCollection.indexOf(`${currentFile}:${currentLine}`),
                linesCollection.length, change
            );
        }

        // Get source code file with provided line
        let newLineData = linesCollection[ind].split(':');
        if (newLineData.length > 2) {
            newLineData = [
                newLineData.slice(0, -1).join(':'),
                newLineData[ newLineData.length - 1 ]
            ];
        }
        if (newLineData.length === 2) {
            this.sourceProcessor.get_source(newLineData[1], newLineData[0]);
        }
    }

    get currentFile() {
        return this.sourceProcessor.title_container.text();
    }

    _clearCache() {
        this._coveredFunctions = null;
        this._uncoveredFunctions = null;
        this._sortedCoveredFunctions = null;
        this._mostCoveredLines = null;
        this.initialFile = this.currentFile;
    }
}