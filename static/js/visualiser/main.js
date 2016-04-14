require([
    "knockout",
    "common/modal/Modal",
    "visualiser/ViewModel",
    "visualiser/panel-action/PanelActionsBuilder",
    "kotemplate!modal-error-content:publisher/templates/error-modal-content.html",
    "domReady!"

], function (ko, Modal, ViewModel, PanelActionsBuilder, errorContentTemplate) {
    ViewModel.loadById(
        window["rootId"],
        "/adapter/certuk_mod/ajax/visualiser/",
        "/adapter/certuk_mod/ajax/visualiser/item/",
        (new PanelActionsBuilder()).build(),
        function (viewModel) {
            ko.applyBindings(
                viewModel,
                document.getElementById("content")
            );
        }, function (error) {
            var errorModal = new Modal({
                title: "Error",
                titleIcon: "glyphicon-warning-sign",
                contentData: error.message,
                contentTemplate: errorContentTemplate.id,
                width: "90%"
            });

            errorModal.getButtonByLabel("OK").callback = history.back.bind(history);
            errorModal.show();
        });
});