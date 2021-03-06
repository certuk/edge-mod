define([
        "dcl/dcl",
        "knockout",
        "./StixObject",
        "./objectTypes/StixObjectType",
        "./objectTypes/EmailMessage",
        "./objectTypes/File",
        "./objectTypes/HttpSession",
        "./objectTypes/NetworkConnection",
        "./objectTypes/SocketAddress",
        "./objectTypes/WindowsRegistryKey",
        "./objectTypes/Port",
        "kotemplate!root-obs:./templates/root-Observable.html",
        "kotemplate!flat-obs:./templates/flat-Observable.html",
        "kotemplate!list-obs:./templates/list-Observables.html"
    ], function (declare, ko, StixObject, StixObjectType, EmailMessageObjectType, FileObjectType, HTTPSessionObjectType, NetworkConnectionObjectType,
                 SocketAddressObjectType, WindowsRegistryKeyObjectType, PortObjectType) {
        "use strict";

        var OBJECT_TYPES = Object.freeze({
            "EmailMessageObjectType": EmailMessageObjectType,
            "FileObjectType": FileObjectType,
            "HTTPSessionObjectType": HTTPSessionObjectType,
            "SocketAddressObjectType": SocketAddressObjectType,
            "WindowsRegistryKeyObjectType": WindowsRegistryKeyObjectType,
            "NetworkConnectionObjectType": NetworkConnectionObjectType,
            "PortObjectType": PortObjectType
        });

        function getObjectType(type) {
            return OBJECT_TYPES[type] || StixObjectType;
        }

        return declare(StixObject, {
            constructor: function (data, stixPackage) {

                this.data = ko.observable(data);
                this.type = ko.computed(function () {
                    var type = stixPackage.safeValueGet(this.id, data, "object.properties.xsi:type", "xsi:type");
                    return type.isEmpty === false ? type : stixPackage.safeValueGet(this.id, data, "observable_composition.operator");
                }, this);
                var objectType = ko.computed(function () {
                    var type = stixPackage.safeGet(data, "object.properties.xsi:type");
                    var ctor = getObjectType(type);
                    return new ctor(this.id, stixPackage.safeGet(data, "object.properties"), stixPackage);
                }, this);
                this.properties = ko.computed(function () {
                    return objectType().properties();
                }, this);
            }
        });
    }
);
