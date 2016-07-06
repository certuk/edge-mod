define([
    "dcl/dcl",
    "knockout",
    "d3",
    "./Link",
    "./Node"
], function (declare, ko, d3, Link, Node) {
    "use strict";

    var RATE_LIMIT = {rateLimit: {timeout: 50, method: "notifyWhenChangesStop"}};

    function isGetterSetter(value) {
        return typeof value === "function" && value.length === 1;
    }

    return declare(null, {
        declaredClass: "Graph",
        constructor: function (graphData) {
            var _d3Layout = d3.layout.force();
            this.d3Layout = ko.computed(function () {
                return _d3Layout;
            });

            // create proxy observables for all [gs]etters on _d3Layout with the default value provided by D3
            var _pendingUpdate = null;
            ko.utils.objectForEach(_d3Layout, function (name, value) {
                if (isGetterSetter(value)) {
                    var proxy = ko.observable(value());
                    proxy.subscribe(function (newValue) {
                        _d3Layout[name](newValue);
                        if (_pendingUpdate) {
                            clearTimeout(_pendingUpdate);
                        }
                        _pendingUpdate = setTimeout(_d3Layout.start.bind(_d3Layout), 50);
                    });
                    this[name] = proxy;
                }
            }.bind(this));

            this.selectedNode = ko.observable(null);
            this.selectedLinkedNodes = ko.computed(function () {
                var selectedNode = this.selectedNode();

                var linkedNodes = {
                    parentOf: {rel_type: 'edge', values: []},
                    childOf: {rel_type: 'childOf', values: []},
                    matches: {rel_type: 'match', values: []},
                    drafts: {rel_type: 'draft', values: []},
                    backlinks: {rel_type: 'backlink', values: []},
                    externalRefs: {rel_type: 'external_ref', values: []}
                };
                ko.utils.arrayForEach(this.nodes(), function (node) {
                    node.isRelated(false);
                    node.isChecked(false);
                });
                if (selectedNode instanceof Node) {
                    var findIndex = selectedNode.index;
                    ko.utils.arrayForEach(this.links(), function (link) {
                        var isRelatedLink = false;
                        if (link.source.index === findIndex) {
                            switch (link.relType()) {
                                case "edge":
                                    linkedNodes.parentOf['values'].push(link.target);
                                    break;
                                case "match":
                                    linkedNodes.matches['values'].push(link.target);
                                    break;
                                case "backlink":
                                    linkedNodes.backlinks['values'].push(link.target);
                                    break;
                                case "draft":
                                    linkedNodes.drafts['values'].push(link.target);
                                    break;
                                case "external_ref":
                                    linkedNodes.externalRefs['values'].push(link.target);
                            }
                            link.target.isRelated(true);
                            isRelatedLink = true;
                        }
                        if (link.target.index === findIndex) {
                            linkedNodes.childOf['values'].push(link.source);
                            link.source.isRelated(true);
                            isRelatedLink = true;
                        }
                        link.isRelated(isRelatedLink);
                    });
                }
                return linkedNodes;
            }, this).extend(RATE_LIMIT);
            this.loadData(graphData);
        },
        nodeAlreadyExists: function (currentNodes, nodeData) {
            for (var i = 0, j = currentNodes.length; i < j; i++) {
                var node = currentNodes[i];
                if (nodeData.depth === node.depth() &&
                    nodeData.id === node.id()) {
                    return node;
                }
            }
            return null;
        },
        linkAlreadyExists: function (currentLinks, sourceData, targetData) {
            for (var i = 0, j = currentLinks.length; i < j; i++) {
                var link = currentLinks[i];
                if (sourceData.depth() === link.source.depth() &&
                    sourceData.id() === link.source.id() &&
                    targetData.depth() === link.target.depth() &&
                    targetData.id() === link.target.id()) {
                    return link;
                }
            }
            return null;
        },
        loadData: function (graphData) {
            this.d3Layout().stop();

            var currentNodes = this.nodes();
            var newNodes = [];

            ko.utils.arrayForEach(graphData.nodes, function (nodeData, i) {
                var existingNode = this.nodeAlreadyExists(currentNodes, nodeData);
                if (!existingNode) {
                    newNodes.push(new Node(nodeData));
                } else {
                    newNodes.push(existingNode);
                }
            }.bind(this));

            this.nodes().splice(0, this.nodes().length);
            this.nodes().push.apply(this.nodes(), newNodes);
            this.nodes.valueHasMutated();


            var /*Node[]*/ _rawNodes = this.nodes.peek();
            var newLinks = [];
            var currentLinks = this.links();
            ko.utils.arrayForEach(graphData.links, function (linkData, i) {
                var existingLink = this.linkAlreadyExists(currentLinks, _rawNodes[linkData.source], _rawNodes[linkData.target]);
                if (existingLink) {
                    newLinks.push(existingLink);
                } else {
                    newLinks.push(new Link(_rawNodes[linkData.source], _rawNodes[linkData.target], linkData.rel_type));
                }
            }.bind(this));

            this.links().splice(0, this.links().length);
            this.links().push.apply(this.links(), newLinks);
            this.links.valueHasMutated();
            this.d3Layout().start();
        },
        applyBindingValues: function (bindingValues) {
            ko.utils.objectForEach(bindingValues, function (name, value) {
                if (ko.isObservable(this[name])) {
                    this[name](value);
                }
            }.bind(this));
        },
        findRootNode: function () {
            return ko.utils.arrayFirst(this.nodes(), function (node) {
                return node.isRoot();
            });
        },
        findNode: function (nodeId) {
            return ko.utils.arrayFirst(this.nodes(), function (node) {
                return nodeId === node.id();
            });
        },
        selectNode: function (nodeId) {
            var oldNode = this.selectedNode();
            if (oldNode instanceof Node) {
                oldNode.isSelected(false);
            }
            var newNode = this.findNode(nodeId);
            if (newNode instanceof Node) {
                newNode.isSelected(true);
                this.selectedNode(newNode);
            }
        },
        call_action: function (action) {
            var checked_node_ids = [];
            ko.utils.arrayForEach(this.nodes(), function (node) {
                if (node.isChecked()) {
                    checked_node_ids.push(node.id());
                }
            });
            action(checked_node_ids, this);
        },
        appendData: function (graphData) {
            //TODO - will need to sort out indexes, etc
        }
    });
});
