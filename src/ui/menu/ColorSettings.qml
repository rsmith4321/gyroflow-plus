// SPDX-License-Identifier: GPL-3.0-or-later

import QtQuick
import QtQuick.Dialogs as QQD
import "../components/"

MenuItem {
    id: root;
    text: qsTr("Color settings");
    iconName: "color";
    objectName: "color";
    innerItem.enabled: window.videoArea.vid.loaded;

    // Keep project, preset and queue color data in the existing export model.
    required property QtObject exportOptions;
    property bool syncing: true;
    property var recentLuts: [];
    property string libraryFolder: settings.value("colorLutLibrary", settings.value("folder-export-lut", ""));
    property var libraryLuts: [];
    // File, recent, folder and camera choices all replace the same active LUT.
    readonly property var availableLuts: {
        const seen = {};
        const urls = [exportOptions.lutUrl].concat(recentLuts, libraryLuts.map(entry => entry[1]));
        return urls.filter(url => {
            if (!url) return false;
            const key = lutKey(url);
            if (seen[key]) return false;
            seen[key] = true;
            return true;
        });
    }
    property var cameraLuts: ({});
    property string pendingCameraId: "";
    readonly property var cameraProfiles: [
        { id: "dji-o4-dlogm", name: "DJI O4 / O4 Pro — D-Log M", url: "https://www.dji.com/downloads/softwares/o4-air-unit-dlog-to-rec709" },
        { id: "dji-action4-dlogm", name: "DJI Osmo Action 4 — D-Log M", url: "https://www.dji.com/downloads/softwares/dji-osmo-action-4-d-log-m-to-rec-709-vivid-lut" },
        { id: "dji-action5-dlogm", name: "DJI Osmo Action 5 Pro — D-Log M", url: "https://www.dji.com/lut" },
        { id: "gopro-gplog", name: "GoPro — GP-Log (match gamut/version)", url: "https://community.gopro.com/s/article/10-Bit-Log-Encoding?language=en_US" },
        { id: "insta-acepro2-ilog", name: "Insta360 Ace Pro 2 — I-Log", url: "https://www.insta360.com/download/i-log" }
    ];
    function refreshLibrary(): void {
        libraryLuts = libraryFolder ? JSON.parse(filesystem.list_lut_files(libraryFolder)) : [];
    }
    function loadCameraLuts(): void {
        try {
            const saved = JSON.parse(settings.value("cameraColorLuts", "{}"));
            if (saved && typeof saved === "object" && !Array.isArray(saved)) {
                const valid = {};
                cameraProfiles.forEach(profile => {
                    const url = saved[profile.id];
                    if (typeof url === "string" && url.startsWith("file:") && /\.cube$/i.test(url)) valid[profile.id] = url;
                });
                cameraLuts = valid;
            }
        } catch (e) { cameraLuts = {}; }
    }
    function acceptLut(url: string): void {
        root.chooseLut(url);
        if (pendingCameraId && !exportOptions.lutPreviewError) {
            const saved = Object.assign({}, cameraLuts);
            saved[pendingCameraId] = url;
            cameraLuts = saved;
            settings.setValue("cameraColorLuts", JSON.stringify(saved));
        }
        pendingCameraId = "";
    }


    function lutKey(url: string): string {
        return filesystem.url_to_path(url);
    }
    function loadRecentLuts(): void {
        try {
            const urls = JSON.parse(settings.value("recentColorLuts", "[]"));
            if (Array.isArray(urls)) {
                recentLuts = urls.filter((url, index) => typeof url === "string"
                    && url.startsWith("file:") && /\.cube$/i.test(url)
                    && urls.findIndex(x => typeof x === "string" && lutKey(x) === lutKey(url)) === index).slice(0, 8);
            }
        } catch (e) { recentLuts = []; }
    }
    function updateLutSelection(): void {
        lutSelector.currentIndex = availableLuts.findIndex(url => lutKey(url) === lutKey(exportOptions.lutUrl));
    }
    function rememberLut(): void {
        const url = exportOptions.lutUrl;
        if (url && !exportOptions.lutPreviewError) {
            const urls = [url].concat(recentLuts.filter(x => lutKey(x) !== lutKey(url))).slice(0, 8);
            if (JSON.stringify(urls) !== JSON.stringify(recentLuts)) {
                recentLuts = urls;
                settings.setValue("recentColorLuts", JSON.stringify(urls));
            }
        }
        updateLutSelection();
    }
    function chooseLut(url: string): void {
        // Reselecting the current file also refreshes its cached preview.
        if (lutKey(exportOptions.lutUrl) === lutKey(url)) exportOptions.lutUrl = "";
        exportOptions.lutUrl = url;
    }

    function syncSliders(): void {
        syncing = true;
        brightnessSlider.value = exportOptions.brightness;
        contrastSlider.value = exportOptions.contrast;
        shadowsSlider.value = exportOptions.shadows;
        highlightsSlider.value = exportOptions.highlights;
        exposureSlider.value = exportOptions.exposure;
        saturationSlider.value = exportOptions.saturation;
        warmthSlider.value = exportOptions.warmth;
        tintSlider.value = exportOptions.tint;
        syncing = false;
    }
    Component.onCompleted: {
        loadRecentLuts();
        loadCameraLuts();
        refreshLibrary();
        syncSliders();
        rememberLut();
    }
    Connections {
        target: root.exportOptions;
        function onLutUrlChanged(): void {
            // Wait for LUT validation before recording a successful selection.
            Qt.callLater(root.rememberLut);
        }
        function onBrightnessChanged(): void { root.syncSliders(); }
        function onContrastChanged(): void { root.syncSliders(); }
        function onShadowsChanged(): void { root.syncSliders(); }
        function onExposureChanged(): void { root.syncSliders(); }
        function onSaturationChanged(): void { root.syncSliders(); }
        function onWarmthChanged(): void { root.syncSliders(); }
        function onTintChanged(): void { root.syncSliders(); }
        function onHighlightsChanged(): void { root.syncSliders(); }
    }

    FileDialog {
        id: lutDialog;
        title: qsTr("Choose a LUT");
        nameFilters: [qsTr("3D LUT files") + " (*.cube *.CUBE)"];
        type: "export-lut";
        onAccepted: root.acceptLut(selectedFile.toString());
        onRejected: root.pendingCameraId = "";
    }
    Label {
        text: qsTr("LUT");
        Column {
            width: parent.width;
            spacing: 8 * dpiScale;
            ComboBox {
                id: lutSelector;
                objectName: "color-lut-selector";
                width: parent.width;
                enabled: root.availableLuts.length > 0;
                model: {
                    const names = root.availableLuts.map(url => filesystem.get_filename(url));
                    const counts = Object.create(null);
                    names.forEach(name => counts[name] = (counts[name] || 0) + 1);
                    return root.availableLuts.map((url, index) => counts[names[index]] > 1
                        ? names[index] + " — " + filesystem.url_to_path(filesystem.get_folder(url)) : names[index]);
                }
                currentIndex: -1;
                displayText: currentIndex >= 0 ? currentText : qsTr("Choose a saved LUT…");
                tooltip: currentIndex >= 0 ? filesystem.url_to_path(root.availableLuts[currentIndex]) : "";
                onModelChanged: Qt.callLater(root.updateLutSelection);
                onActivated: index => root.chooseLut(root.availableLuts[index]);
            }
            Row {
                spacing: 6 * dpiScale;
                Button {
                    text: qsTr("Choose file…");
                    onClicked: { root.pendingCameraId = ""; lutDialog.open2(); }
                }
                Button {
                    objectName: "clear-color-lut";
                    text: qsTr("Clear");
                    visible: !!root.exportOptions.lutUrl;
                    onClicked: root.exportOptions.lutUrl = "";
                }
            }
            BasicText {
                width: parent.width;
                leftPadding: 0;
                text: qsTr("One LUT at a time. Choosing another replaces it.");
                wrapMode: Text.WordWrap;
                font.pixelSize: 10 * dpiScale;
                opacity: 0.7;
            }
        }
    }
    InfoMessageSmall {
        show: !!root.exportOptions.lutPreviewError;
        type: InfoMessage.Error;
        text: root.exportOptions.lutPreviewError;
    }
    Rectangle {
        width: parent.width;
        height: lutStatus.height + 24 * dpiScale;
        visible: !!root.exportOptions.lutUrl && !root.exportOptions.lutPreviewError;
        radius: 6 * dpiScale;
        color: Qt.rgba(0.22, 0.70, 0.44, 0.10);
        border.color: Qt.rgba(0.22, 0.70, 0.44, 0.35);
        Column {
            id: lutStatus;
            x: 12 * dpiScale;
            y: 12 * dpiScale;
            width: parent.width - 24 * dpiScale;
            spacing: 5 * dpiScale;
            BasicText {
                leftPadding: 0;
                text: qsTr("✓ Active LUT");
                font.bold: true;
                color: "#54bf85";
            }
            BasicText {
                width: parent.width;
                leftPadding: 0;
                text: filesystem.get_filename(root.exportOptions.lutUrl);
                wrapMode: Text.Wrap;
            }
            BasicText {
                width: parent.width;
                leftPadding: 0;
                text: root.exportOptions.previewColors ? qsTr("Applied to preview and export.") : qsTr("Applied to export. Preview colors are switched off.");
                font.pixelSize: 11 * dpiScale;
                opacity: 0.7;
                wrapMode: Text.WordWrap;
            }
        }
    }

    MenuItem {
        text: qsTr("Find && organize LUTs"); // "&&" shows one "&"; a single one marks a shortcut key
        objectName: "color-lut-library";
        opened: false;
        QQD.FolderDialog {
            id: libraryDialog;
            title: qsTr("Choose your LUT folder");
            onAccepted: {
                root.libraryFolder = selectedFolder.toString();
                filesystem.folder_access_granted(selectedFolder);
                filesystem.save_allowed_folders();
                settings.setValue("colorLutLibrary", root.libraryFolder);
                settings.setValue("folder-export-lut", root.libraryFolder);
                root.refreshLibrary();
            }
        }
        Row {
            spacing: 6 * dpiScale;
            Button {
                text: qsTr("Choose folder…");
                onClicked: { if (root.libraryFolder) libraryDialog.currentFolder = root.libraryFolder; libraryDialog.open(); }
            }
            Button {
                text: qsTr("Refresh");
                enabled: !!root.libraryFolder;
                onClicked: root.refreshLibrary();
            }
        }
        BasicText {
            width: parent.width;
            text: root.libraryFolder ? filesystem.display_url(root.libraryFolder) : qsTr("Choose a folder to add its .cube files to the LUT dropdown above.");
            wrapMode: Text.Wrap;
            font.pixelSize: 10 * dpiScale;
            opacity: 0.7;
        }
        Label {
            text: qsTr("Official camera LUTs");
            ComboBox {
                id: cameraSelector;
                width: parent.width;
                model: root.cameraProfiles.map(profile => profile.name);
                currentIndex: -1;
                displayText: currentIndex >= 0 ? currentText : qsTr("Choose a camera/profile…");
            }
        }
        Row {
            spacing: 6 * dpiScale;
            Button {
                text: qsTr("Apply saved LUT");
                enabled: cameraSelector.currentIndex >= 0 && !!root.cameraLuts[root.cameraProfiles[cameraSelector.currentIndex].id];
                onClicked: root.chooseLut(root.cameraLuts[root.cameraProfiles[cameraSelector.currentIndex].id]);
            }
            Button {
                text: qsTr("Choose file…");
                enabled: cameraSelector.currentIndex >= 0;
                onClicked: { root.pendingCameraId = root.cameraProfiles[cameraSelector.currentIndex].id; lutDialog.open2(); }
            }
        }
        LinkButton {
            text: qsTr("Get the official camera LUT…");
            visible: cameraSelector.currentIndex >= 0;
            onClicked: Qt.openUrlExternally(root.cameraProfiles[cameraSelector.currentIndex].url);
        }
        BasicText {
            width: parent.width;
            wrapMode: Text.WordWrap;
            font.pixelSize: 10 * dpiScale;
            opacity: 0.7;
            text: qsTr("Download the matching official LUT, then choose its file to apply it and remember it for this camera profile. Applying a saved LUT replaces the active LUT above. Camera files are not bundled; match the LUT to your recording’s log profile.");
        }
    }

    Label {
        text: qsTr("Exposure");
        SliderWithField {
            id: exposureSlider;
            onValueChanged: if (!root.syncing) root.exportOptions.exposure = value;
            doubleClickResetEnabled: true;
            width: parent.width;
            from: -2; to: 2; field.from: -2; field.to: 2; defaultValue: 0; precision: 2;
        }
    }
    Label {
        text: qsTr("Temperature");
        SliderWithField {
            id: warmthSlider;
            onValueChanged: if (!root.syncing) root.exportOptions.warmth = value;
            doubleClickResetEnabled: true;
            width: parent.width;
            from: -100; to: 100; field.from: -100; field.to: 100; defaultValue: 0; precision: 0; unit: "%";
        }
    }
    Label {
        text: qsTr("Tint");
        SliderWithField {
            id: tintSlider;
            onValueChanged: if (!root.syncing) root.exportOptions.tint = value;
            doubleClickResetEnabled: true;
            width: parent.width;
            from: -100; to: 100; field.from: -100; field.to: 100; defaultValue: 0; precision: 0; unit: "%";
        }
    }
    Label {
        text: qsTr("Brightness");
        SliderWithField {
            id: brightnessSlider;
            onValueChanged: if (!root.syncing) root.exportOptions.brightness = value;
            doubleClickResetEnabled: true;
            width: parent.width;
            from: -50; to: 50; field.from: -50; field.to: 50; defaultValue: 0; precision: 0; unit: "%";
        }
    }
    Label {
        text: qsTr("Contrast");
        SliderWithField {
            id: contrastSlider;
            onValueChanged: if (!root.syncing) root.exportOptions.contrast = value;
            doubleClickResetEnabled: true;
            width: parent.width;
            from: -50; to: 50; field.from: -50; field.to: 50; defaultValue: 0; precision: 0; unit: "%";
        }
    }
    Label {
        text: qsTr("Highlights");
        SliderWithField {
            id: highlightsSlider;
            onValueChanged: if (!root.syncing) root.exportOptions.highlights = value;
            doubleClickResetEnabled: true;
            width: parent.width;
            from: -50; to: 50; field.from: -50; field.to: 50; defaultValue: 0; precision: 0; unit: "%";
        }
    }
    Label {
        text: qsTr("Shadows");
        SliderWithField {
            id: shadowsSlider;
            onValueChanged: if (!root.syncing) root.exportOptions.shadows = value;
            doubleClickResetEnabled: true;
            width: parent.width;
            from: -50; to: 50; field.from: -50; field.to: 50; defaultValue: 0; precision: 0; unit: "%";
        }
    }
    Label {
        text: qsTr("Saturation");
        SliderWithField {
            id: saturationSlider;
            onValueChanged: if (!root.syncing) root.exportOptions.saturation = value;
            doubleClickResetEnabled: true;
            width: parent.width;
            from: -100; to: 100; field.from: -100; field.to: 100; defaultValue: 0; precision: 0; unit: "%";
        }
    }
    InfoMessageSmall {
        show: !!root.exportOptions.gradePreviewError;
        type: InfoMessage.Error;
        text: root.exportOptions.gradePreviewError;
    }
    InfoMessageSmall {
        show: !!root.exportOptions.tonePreviewError;
        type: InfoMessage.Error;
        text: root.exportOptions.tonePreviewError;
    }
    InfoMessageSmall {
        show: !!root.exportOptions.ocioPreviewError;
        type: InfoMessage.Error;
        text: root.exportOptions.ocioPreviewError;
    }
    InfoMessageSmall {
        show: root.exportOptions.ocioPreviewBusy;
        type: InfoMessage.Info;
        text: qsTr("Updating color preview…");
    }
    Row {
        spacing: 8 * dpiScale;
        CheckBox {
            text: qsTr("Preview colors");
            checked: root.exportOptions.previewColors;
            // Enter and accessibility actions may change checked without emitting toggled.
            onCheckedChanged: root.exportOptions.previewColors = checked;
        }
        Button {
            text: qsTr("Reset adjustments");
            enabled: root.exportOptions.brightness !== 0 || root.exportOptions.contrast !== 0
                || root.exportOptions.shadows !== 0 || root.exportOptions.highlights !== 0
                || root.exportOptions.exposure !== 0 || root.exportOptions.saturation !== 0 || root.exportOptions.warmth !== 0 || root.exportOptions.tint !== 0;
            onClicked: { root.exportOptions.brightness = 0; root.exportOptions.contrast = 0; root.exportOptions.shadows = 0; root.exportOptions.highlights = 0; root.exportOptions.exposure = 0; root.exportOptions.saturation = 0; root.exportOptions.warmth = 0; root.exportOptions.tint = 0; }
        }
    }
    BasicText {
        width: parent.width;
        wrapMode: Text.WordWrap;
        font.pixelSize: 11 * dpiScale;
        opacity: 0.7;
        text: qsTr("Choose a viewing LUT for log footage. Adjustments follow the LUT and are included in export. Exposure adjusts display light; temperature and tint provide relative color balance. Originals stay untouched; saved projects keep your settings editable. Double-click a slider to reset it.");
    }

}
