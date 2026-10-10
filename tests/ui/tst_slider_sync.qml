// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtTest
import "../../src/ui/components" as App

TestCase {
    name: "SharedSliderSync"
    width: 400; height: 100
    visible: true
    when: windowShown
    property real dpiScale: 1
    property bool isMobile: false
    property color styleAccentColor: "#80bfff"
    property color styleTextColor: "white"
    property color styleBackground2: "#222222"
    property color styleButtonColor: "#333333"
    property color styleSliderBackground: "#555555"
    property color styleSliderHandle: "#999999"
    property color stylePopupBorder: "#555555"
    property string styleFont: "Helvetica"
    QtObject {
        id: controller
        signal keyframe_value_updated(string keyframe, real value)
        signal gyroflow_file_loaded(var obj)
        property int writes: 0
        function set_keyframe(key, timestamp, value) { writes += 1; }
    }
    QtObject {
        id: window
        property var videoArea: ({ timeline: { getTimestampUs: () => 123 } })
    }
    App.SliderWithField {
        id: control
        width: 360
        from: -50; to: 50
        field.from: -50; field.to: 50
        defaultValue: 0; precision: 0
        doubleClickResetEnabled: true
    }
    function test_exact_reset_data() {
        return [
            {tag: "negative_fraction", v: -0.17},
            {tag: "positive_fraction", v: 0.17},
            {tag: "negative_grade", v: -18.713},
            {tag: "positive_grade", v: 28.173},
            {tag: "minimum", v: -50},
            {tag: "maximum", v: 50}
        ];
    }
    function test_exact_reset(data) {
        control.slider.value = data.v;
        wait(2);
        control.value = 0;
        wait(2);
        compare(control.value, 0, "public control value");
        compare(control.field.value, 0, "field numeric value");
        compare(control.slider.value, 0, "slider numeric value");
        compare(control.slider.position, 0.5, "centered thumb");
    }
    function test_consecutive_slider_updates() {
        control.value = 5;
        wait(2);
        control.slider.value = 0;
        control.slider.value = 7;
        wait(2);
        compare(control.value, 7, "latest slider input reaches model");
        compare(control.field.value, 7, "field matches latest input");
        compare(control.slider.value, 7, "thumb matches model");
    }
    function test_programmatic_and_scaled_values() {
        control.value = -13;
        compare(control.field.value, -13);
        compare(control.slider.value, -13);
        control.scaler = 2;
        control.value = 9;
        compare(control.field.value, 18);
        compare(control.slider.value, 18);
        control.slider.value = 8;
        compare(control.value, 4);
        control.value = 0;
        compare(control.field.value, 0);
        compare(control.slider.value, 0);
        control.scaler = 1;
    }
    function test_keyframe_display_update_does_not_write_back() {
        control.keyframe = "test-color";
        control.keyframesEnabled = true;
        control.value = 3;
        const before = controller.writes;
        controller.keyframe_value_updated("test-color", 11);
        compare(control.value, 3, "keyframe display does not replace base value");
        compare(control.field.value, 11);
        compare(control.slider.value, 11);
        compare(controller.writes, before, "display update does not write a keyframe");
        control.slider.value = 12;
        compare(control.value, 12);
        compare(controller.writes, before + 1, "user input writes one keyframe");
        control.keyframesEnabled = false;
        control.keyframe = "";
        control.value = 0;
    }

}
