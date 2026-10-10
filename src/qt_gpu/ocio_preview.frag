// SPDX-License-Identifier: GPL-3.0-or-later
// Official OCIO generation supplies both LUT sampling and grading operations.
#version 440
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
};
layout(binding = 1) uniform sampler2D source;
// GP_OCIO_GRADE

void main() {
    vec4 pixel = texture(source, qt_TexCoord0);
    vec3 rgb = pixel.a > 0.0 ? pixel.rgb / pixel.a : vec3(0.0);
    rgb = applyOcioGrade(vec4(rgb, pixel.a)).rgb;
    fragColor = vec4(rgb * pixel.a, pixel.a) * qt_Opacity;
}
