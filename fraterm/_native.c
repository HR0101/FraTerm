#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define MAX_CELL_BYTES 64
#define LINE_SUFFIX_BYTES 5

static const char UPPER_HALF_BLOCK[] = "\xE2\x96\x80";
static const char RESET[] = "\x1b[0m";

static int append_format(
  char *output,
  Py_ssize_t capacity,
  Py_ssize_t *offset,
  const char *format,
  unsigned int first,
  unsigned int second,
  unsigned int third,
  unsigned int fourth,
  unsigned int fifth,
  unsigned int sixth
) {
  int written = snprintf(
    output + *offset,
    (size_t)(capacity - *offset),
    format,
    first,
    second,
    third,
    fourth,
    fifth,
    sixth
  );
  if (written < 0 || (Py_ssize_t)written >= capacity - *offset) {
    PyErr_SetString(PyExc_RuntimeError, "ANSI出力バッファが不足しました．");
    return -1;
  }
  *offset += (Py_ssize_t)written;
  return 0;
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
  char *output = NULL;
  PyObject *result = NULL;

  (void)self;

  if (!PyArg_ParseTuple(args, "O:renderHalfBlock", &frame)) {
    return NULL;
  }

  if (PyObject_GetBuffer(frame, &view, PyBUF_STRIDES | PyBUF_FORMAT) < 0) {
    return NULL;
  }

  if (
    view.ndim != 3 || view.itemsize != 1 || view.shape == NULL ||
    view.strides == NULL || view.shape[2] != 3 ||
    (view.format != NULL && strcmp(view.format, "B") != 0)
  ) {
    PyErr_SetString(
      PyExc_ValueError,
      "uint8型で shape=(rows * 2, columns, 3) のBGR画像が必要です．"
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
      const uint8_t *top_bgr = (const uint8_t *)view.buf +
        (row * 2) * view.strides[0] + column * view.strides[1];
      const uint8_t *bottom_bgr = top_bgr + view.strides[0];
      uint8_t top[3] = {
        top_bgr[2 * view.strides[2]],
        top_bgr[1 * view.strides[2]],
        top_bgr[0 * view.strides[2]],
      };
      uint8_t bottom[3] = {
        bottom_bgr[2 * view.strides[2]],
        bottom_bgr[1 * view.strides[2]],
        bottom_bgr[0 * view.strides[2]],
      };
      int top_changed = !has_previous || memcmp(top, previous_top, 3) != 0;
      int bottom_changed =
        !has_previous || memcmp(bottom, previous_bottom, 3) != 0;

      if (top_changed && bottom_changed) {
        if (append_format(
          output,
          capacity,
          &offset,
          "\x1b[38;2;%u;%u;%u;48;2;%u;%u;%um",
          top[0],
          top[1],
          top[2],
          bottom[0],
          bottom[1],
          bottom[2]
        ) < 0) {
          goto cleanup;
        }
      } else if (top_changed) {
        if (append_format(
          output,
          capacity,
          &offset,
          "\x1b[38;2;%u;%u;%um",
          top[0],
          top[1],
          top[2],
          0,
          0,
          0
        ) < 0) {
          goto cleanup;
        }
      } else if (bottom_changed) {
        if (append_format(
          output,
          capacity,
          &offset,
          "\x1b[48;2;%u;%u;%um",
          bottom[0],
          bottom[1],
          bottom[2],
          0,
          0,
          0
        ) < 0) {
          goto cleanup;
        }
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

static PyMethodDef native_methods[] = {
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
  native_methods
};

PyMODINIT_FUNC PyInit__native(void) {
  return PyModule_Create(&native_module);
}
