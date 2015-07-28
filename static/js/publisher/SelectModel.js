define(["knockout", "knockout-dragdrop", "dcl/dcl"], function (ko, kos, declare) {

    function filterIncidentObject (response) {
        var incident = {};
        ko.utils.objectForEach(response||{}, function (name, value) {
            if (name === "edges") {
                ko.utils.arrayForEach(value, function (edge) {
                    var type = edge["ty"];
                    if (type === "ttp" || type === "ind" || type === "coa" || type === "inc") {
                        edge._selectable = ko.observable(true);
                    } else {
                        edge._selectable = ko.observable(false);
                    }
                    edge._visible = ko.observable(true);
                });
                incident.edges = value;
            } else if (name === "success" || name === "error_message") {
                // ignore these properties
            } else {
                incident[name] = value;
            }
        });
        return incident;
    }

    return declare(null, {
        constructor: function () {
            this.search = ko.observable("");
            this.results = ko.observableArray([]);
            this.hasResults = ko.computed(function () {
                return this.results().length > 0;
            }, this);
            this.selectedId = ko.observable("");
            this.selectedIncident = ko.observable(null);
            this.availableEdges = ko.observableArray([]);
            this.selectedEdges = ko.observableArray([]);

            this.search.subscribe(this._onSearchChanged, this);
            this.selectedId.subscribe(this._onSelectionChanged, this);

            this._onSearchChanged(this.search());
        },

        _onSearchChanged: function (/*String*/ newValue) {
            postJSON("/catalog/ajax/load_catalog/", {
                search: newValue,
                size: 10,
                type: "inc"
            }, this._onSearchResponseReceived.bind(this));
        },

        _onSearchResponseReceived: function (response) {
            if (response["success"]) {
                this.results(response["data"]);
            } else {
                alert(response["message"]);
            }
        },

        select: function (incident) {
            this.selectedId(incident.id);
        },

        unselect: function () {
            this.selectedId(null);
        },

        _onSelectionChanged: function (newId) {
            this.availableEdges.removeAll();
            this.selectedEdges.removeAll();
            if (newId) {
                postJSON("/catalog/ajax/get_object/", {
                    id: newId
                }, this._onSelectionResponseReceived.bind(this));
            } else {
                this.selectedIncident(null);
            }
        },

        _onSelectionResponseReceived: function (response) {
            if (response["success"]) {
                var incident = filterIncidentObject(response);
                this.selectedIncident(incident);
                this.availableEdges(incident.edges);
            } else {
                alert(response["error_message"]);
            }
        },

        onSelected: function (data, model) {
            data._visible(false);
            this.selectedEdges.push(data);
        },

        onUnselected: function (data, model) {
            this.selectedEdges.remove(data);
            data._visible(true);
        }
    });
});
