class ReportGraph {
    constructor(container) {
        this.container = container;
        this.vertexMap = null;

        // Checks if browser is supported
        if (!mxClient.isBrowserSupported()) {
            return err_notify('Browser is not supported!');
        }

        this.graph = this._init();
        this.parent = this.graph.getDefaultParent();

        // Creates a layout algorithm to be used with the graph
        this.layout = new mxHierarchicalLayout(this.graph);
    }

    _init() {
        // Creates the graph inside the given container
        let graph = new mxGraph(this.container);
        graph.setCellsMovable(false);
        graph.setAutoSizeCells(true);
        graph.isCellsLocked = () => true;
        graph.isCellsBendable = () => false;
        graph.setPanning(true);
        graph.panningHandler.useLeftButtonForPanning = true;

        let graphGetPreferredSizeForCell = graph.getPreferredSizeForCell;
        graph.getPreferredSizeForCell = function(cell) {
            let result = graphGetPreferredSizeForCell.apply(this, arguments);
            result.width += 10;
            result.height = 30;
            return result;
        };

        mxEvent.addMouseWheelListener((evt, up) => {
            if (mxEvent.isConsumed(evt)) {
                return;
            }
            if (up) {
                graph.zoomIn();
            } else {
                graph.zoomOut();
            }
            mxEvent.consume(evt);
        }, this.container);

        if (mxClient.IS_QUIRKS) {
            this.container.style.overflow = 'hidden';
            new mxDivResizer(this.container);
        }

        // Changes the default vertex style
        let style = graph.getStylesheet().getDefaultVertexStyle();
        style[mxConstants.STYLE_PERIMETER] = mxPerimeter.RectanglePerimeter;
        style[mxConstants.STYLE_GRADIENTCOLOR] = 'white';
        style[mxConstants.STYLE_PERIMETER_SPACING] = 0;
        style[mxConstants.STYLE_ROUNDED] = true;

        // Changes the default vertex style
        let edgeStyle = graph.getStylesheet().getDefaultEdgeStyle();
        edgeStyle[mxConstants.STYLE_ROUNDED] = true;
        edgeStyle[mxConstants.STYLE_ARCSIZE] = 40;

        return graph;
    }

    openFullScreen() {
        const bounds = this.graph.getGraphBounds();
        mxUtils.show(this.graph, null, bounds.x, bounds.y);  // bounds.width, bounds.height
    }

    clearGraph() {
        if (!this.vertexMap) {
            return;
        }
        this.graph.removeCells(Array.from(this.vertexMap.values()));
        this.vertexMap = null;
    }

    updateGraph(data) {
        this.clearGraph();
        this.layout = new mxHierarchicalLayout(this.graph);
        this.layout.interRankCellSpacing = 60;
        this.layout.levelDistance = 30;

        // Load cells and layouts the graph
        this.graph.getModel().beginUpdate();
        try {
            this.vertexMap = new Map();
            for (const [key, value] of data.nodes) {
                const newCell = this.graph.insertVertex(this.parent, null, value, 0, 0, 80, 30);
                this.graph.updateCellSize(newCell, true);
                this.vertexMap.set(key, newCell);
            }
            for (const [key, value] of data.links) {
                const v1 = this.vertexMap.get(key),
                    v2 = this.vertexMap.get(value);
                if (v1 && v2) {
                    this.graph.insertEdge(this.parent, null, '', v1, v2);
                }
            }

            // Executes the layout
            this.layout.execute(this.parent);
        }
        finally {
            this.graph.getModel().endUpdate();

            const bounds = this.graph.getGraphBounds();
            let newX = bounds.x, newY = bounds.y, newW = bounds.width + 20, newH = bounds.height + 20;
            if (newX < 20) {
                newX = 20;
                newW += 20;
            }
            if (newY < 20) {
                newY = 20;
                newH += 20;
            }
            this.graph.getModel().setGeometry(this.graph.getDefaultParent(), new mxGeometry(newX, newY, newW, newH));
        }
    }

    fromDotData(content) {
        let data = {
            name: null,
            nodes: new Map(),
            links: []
        };
        let rowsArr = content.split('\n').map(x => x.trim());
        const re1 = new RegExp(/digraph\s*"(.*)"/),
            re2 = new RegExp(/([\-\d]+)\s*\[label="(.*)"]/),
            re3 = new RegExp(/([\-\d]+)\s*->\s*([\-\d]+)/);
        let match;
        for (let rowStr of rowsArr) {
            match = rowStr.match(re1);
            if (match) {
                data.name = match[1];
                continue
            }
            match = rowStr.match(re2);
            if (match) {
                data.nodes.set(match[1], match[2].replace('\\l', ''));
                continue
            }
            match = rowStr.match(re3);
            if (match) {
                data.links.push([match[1], match[2]]);
            }
        }
        this.updateGraph(data);
    }
}