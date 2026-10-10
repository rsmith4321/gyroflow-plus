# Shared QML slider regression

Run against an installed Qt Quick Test runtime from the repository root:

```sh
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software QT_QUICK_CONTROLS_STYLE=Basic \
  qmltestrunner -input tests/ui -platform offscreen
```

The test imports the application components directly. It checks that consecutive
slider inputs in one event-loop turn reach the model, numeric resets center the
thumb, scaled controls keep their values consistent, and keyframe display updates
do not write back while user input writes one keyframe. It needs no media,
application settings or foreground window.

This is a component regression, not native application, video preview/export,
platform package, or double-click gesture acceptance. The test does not synthesize
double-clicks. Its mock controller checks keyframe calls without running the
application's keyframe implementation.
