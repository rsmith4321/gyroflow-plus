// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif
void * gp_ocio_create(const double * parameters, char * error, size_t capacity);
void * gp_ocio_create_with_lut(const double * parameters, const char * lut_path, char * error, size_t capacity);
void gp_ocio_destroy(void * processor);
int gp_ocio_apply(const void * processor, float * r, float * g, float * b,
                  uint32_t width, uint32_t height, size_t r_stride, size_t g_stride,
                  size_t b_stride, char * error, size_t capacity);
size_t gp_ocio_shader(const void * processor, char * output, size_t output_capacity,
                      char * error, size_t capacity);
size_t gp_ocio_texture3d(const void * processor, float * output, size_t float_capacity,
                         uint32_t * edge, char * error, size_t capacity);
#ifdef __cplusplus
}
#endif
