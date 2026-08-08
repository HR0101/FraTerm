#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <stdint.h>
#include <string.h>

#define MAX_CELL_BYTES 64
#define LINE_SUFFIX_BYTES 5

static const char UPPER_HALF_BLOCK[] = "\xE2\x96\x80";
static const char RESET[] = "\x1b[0m";

static void append_literal(
  char *output,
  Py_ssize_t *offset,
  const char *literal,
  Py_ssize_t length
) {
  memcpy(output + *offset, literal, (size_t)length);
  *offset += length;
}

static void append_color_value(
  char *output,
  Py_ssize_t *offset,
  uint8_t value
) {
  if (value >= 100) {
    output[(*offset)++] = (char)('0' + value / 100);
    value = (uint8_t)(value % 100);
    output[(*offset)++] = (char)('0' + value / 10);
  } else if (value >= 10) {
    output[(*offset)++] = (char)('0' + value / 10);
  }
  output[(*offset)++] = (char)('0' + value % 10);
}

static void append_rgb(
  char *output,
  Py_ssize_t *offset,
  const uint8_t color[3]
) {
  append_color_value(output, offset, color[0]);
  output[(*offset)++] = ';';
  append_color_value(output, offset, color[1]);
  output[(*offset)++] = ';';
  append_color_value(output, offset, color[2]);
}

static PyObject *render_half_block(PyObject *self, PyObject *args) {
  PyObject *frame;
  Py_buffer view;
  Py_ssize_t height;
  Py_ssize_t width;
  Py_ssize_t rows;
  Py_ssize_t cell_count;
  Py_ssize_t capacity;
  Py_ssize_t offset = 0;
  int is_grayscale;
  char *output = NULL;
  PyObject *result = NULL;

  (void)self;

  if (!PyArg_ParseTuple(args, "O:renderHalfBlock", &frame)) {
    return NULL;
  }

  if (PyObject_GetBuffer(frame, &view, PyBUF_STRIDES | PyBUF_FORMAT) < 0) {
    return NULL;
  }

  is_grayscale = view.ndim == 2;
  if (
    (view.ndim != 2 && view.ndim != 3) || view.itemsize != 1 ||
    view.shape == NULL || view.strides == NULL ||
    (!is_grayscale && view.shape[2] != 3) ||
    (view.format != NULL && strcmp(view.format, "B") != 0)
  ) {
    PyErr_SetString(
      PyExc_ValueError,
      "uint8型で2次元のグレースケール画像，または"
      "shape=(rows * 2, columns, 3) のBGR画像が必要です．"
    );
    goto cleanup;
  }

  height = view.shape[0];
  width = view.shape[1];
  if (height <= 0 || width <= 0 || height % 2 != 0) {
    PyErr_SetString(
      PyExc_ValueError,
      "画像の幅は正，かつ高さは正の偶数である必要があります．"
    );
    goto cleanup;
  }
  rows = height / 2;

  if (width > PY_SSIZE_T_MAX / rows) {
    PyErr_NoMemory();
    goto cleanup;
  }
  cell_count = width * rows;
  if (
    cell_count > (PY_SSIZE_T_MAX - 1) / MAX_CELL_BYTES ||
    rows > (PY_SSIZE_T_MAX - cell_count * MAX_CELL_BYTES - 1) /
      LINE_SUFFIX_BYTES
  ) {
    PyErr_NoMemory();
    goto cleanup;
  }
  capacity =
    cell_count * MAX_CELL_BYTES + rows * LINE_SUFFIX_BYTES + 1;
  output = PyMem_Malloc((size_t)capacity);
  if (output == NULL) {
    PyErr_NoMemory();
    goto cleanup;
  }

  for (Py_ssize_t row = 0; row < rows; row++) {
    uint8_t previous_top[3] = {0, 0, 0};
    uint8_t previous_bottom[3] = {0, 0, 0};
    int has_previous = 0;

    for (Py_ssize_t column = 0; column < width; column++) {
      const uint8_t *top_pixel = (const uint8_t *)view.buf +
        (row * 2) * view.strides[0] + column * view.strides[1];
      const uint8_t *bottom_pixel = top_pixel + view.strides[0];
      uint8_t top[3];
      uint8_t bottom[3];

      if (is_grayscale) {
        top[0] = top[1] = top[2] = top_pixel[0];
        bottom[0] = bottom[1] = bottom[2] = bottom_pixel[0];
      } else {
        top[0] = top_pixel[2 * view.strides[2]];
        top[1] = top_pixel[1 * view.strides[2]];
        top[2] = top_pixel[0 * view.strides[2]];
        bottom[0] = bottom_pixel[2 * view.strides[2]];
        bottom[1] = bottom_pixel[1 * view.strides[2]];
        bottom[2] = bottom_pixel[0 * view.strides[2]];
      }
      int top_changed = !has_previous || memcmp(top, previous_top, 3) != 0;
      int bottom_changed =
        !has_previous || memcmp(bottom, previous_bottom, 3) != 0;

      if (top_changed && bottom_changed) {
        append_literal(output, &offset, "\x1b[38;2;", 7);
        append_rgb(output, &offset, top);
        append_literal(output, &offset, ";48;2;", 6);
        append_rgb(output, &offset, bottom);
        output[offset++] = 'm';
      } else if (top_changed) {
        append_literal(output, &offset, "\x1b[38;2;", 7);
        append_rgb(output, &offset, top);
        output[offset++] = 'm';
      } else if (bottom_changed) {
        append_literal(output, &offset, "\x1b[48;2;", 7);
        append_rgb(output, &offset, bottom);
        output[offset++] = 'm';
      }

      memcpy(output + offset, UPPER_HALF_BLOCK, sizeof(UPPER_HALF_BLOCK) - 1);
      offset += (Py_ssize_t)(sizeof(UPPER_HALF_BLOCK) - 1);
      memcpy(previous_top, top, 3);
      memcpy(previous_bottom, bottom, 3);
      has_previous = 1;
    }

    memcpy(output + offset, RESET, sizeof(RESET) - 1);
    offset += (Py_ssize_t)(sizeof(RESET) - 1);
    if (row + 1 < rows) {
      output[offset++] = '\n';
    }
  }

  result = PyUnicode_DecodeUTF8(output, offset, "strict");

cleanup:
  PyMem_Free(output);
  PyBuffer_Release(&view);
  return result;
}

static PyObject *render_ascii(PyObject *self, PyObject *args) {
  PyObject *image;
  PyObject *charset;
  Py_buffer view;
  Py_ssize_t height;
  Py_ssize_t width;
  Py_ssize_t charset_length;
  Py_ssize_t output_length;
  Py_ssize_t output_offset = 0;
  int charset_kind;
  int output_kind;
  void *charset_data;
  void *output_data;
  Py_UCS4 max_character;
  PyObject *result = NULL;

  (void)self;

  if (!PyArg_ParseTuple(args, "OO:renderAscii", &image, &charset)) {
    return NULL;
  }
  if (!PyUnicode_Check(charset)) {
    PyErr_SetString(PyExc_TypeError, "文字セットは文字列で指定してください．");
    return NULL;
  }
  charset_length = PyUnicode_GetLength(charset);
  if (charset_length <= 0) {
    PyErr_SetString(PyExc_ValueError, "文字セットが空です．");
    return NULL;
  }

  if (PyObject_GetBuffer(image, &view, PyBUF_STRIDES | PyBUF_FORMAT) < 0) {
    return NULL;
  }
  if (
    view.ndim != 2 || view.itemsize != 1 || view.shape == NULL ||
    view.strides == NULL ||
    (view.format != NULL && strcmp(view.format, "B") != 0)
  ) {
    PyErr_SetString(
      PyExc_ValueError,
      "uint8型の2次元グレースケール画像が必要です．"
    );
    goto cleanup;
  }

  height = view.shape[0];
  width = view.shape[1];
  if (height <= 0 || width <= 0) {
    PyErr_SetString(PyExc_ValueError, "画像の幅と高さは正である必要があります．");
    goto cleanup;
  }
  if (width > (PY_SSIZE_T_MAX - height + 1) / height) {
    PyErr_NoMemory();
    goto cleanup;
  }
  output_length = width * height + height - 1;

  charset_kind = PyUnicode_KIND(charset);
  charset_data = PyUnicode_DATA(charset);
  max_character = (Py_UCS4)'\n';
  for (Py_ssize_t row = 0; row < height; row++) {
    for (Py_ssize_t column = 0; column < width; column++) {
      const uint8_t *pixel = (const uint8_t *)view.buf +
        row * view.strides[0] + column * view.strides[1];
      Py_ssize_t index =
        (Py_ssize_t)pixel[0] * (charset_length - 1) / 255;
      Py_UCS4 character =
        PyUnicode_READ(charset_kind, charset_data, index);
      if (character > max_character) {
        max_character = character;
      }
    }
  }

  result = PyUnicode_New(output_length, max_character);
  if (result == NULL) {
    goto cleanup;
  }
  output_kind = PyUnicode_KIND(result);
  output_data = PyUnicode_DATA(result);

  for (Py_ssize_t row = 0; row < height; row++) {
    for (Py_ssize_t column = 0; column < width; column++) {
      const uint8_t *pixel = (const uint8_t *)view.buf +
        row * view.strides[0] + column * view.strides[1];
      Py_ssize_t index =
        (Py_ssize_t)pixel[0] * (charset_length - 1) / 255;
      Py_UCS4 character =
        PyUnicode_READ(charset_kind, charset_data, index);
      PyUnicode_WRITE(output_kind, output_data, output_offset++, character);
    }
    if (row + 1 < height) {
      PyUnicode_WRITE(
        output_kind,
        output_data,
        output_offset++,
        (Py_UCS4)'\n'
      );
    }
  }

cleanup:
  PyBuffer_Release(&view);
  return result;
}

static PyMethodDef native_methods[] = {
  {
    "renderAscii",
    render_ascii,
    METH_VARARGS,
    PyDoc_STR("グレースケール画像を指定文字セットの文字列へ変換する．")
  },
  {
    "renderHalfBlock",
    render_half_block,
    METH_VARARGS,
    PyDoc_STR("BGR画像をANSI True Colorのハーフブロック文字列へ変換する．")
  },
  {NULL, NULL, 0, NULL}
};

static struct PyModuleDef native_module = {
  PyModuleDef_HEAD_INIT,
  "_native",
  "FraTermの描画ホットパスを高速化するC拡張．",
  -1,
  native_methods,
  NULL,
  NULL,
  NULL,
  NULL
};

PyMODINIT_FUNC PyInit__native(void) {
  return PyModule_Create(&native_module);
}
