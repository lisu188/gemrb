#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
#
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise the real SaveGame binding with CPython and controlled save storage.

The sprite conversion boundary rejects null pointers, matching its production
contract. This covers argument handling, not save serialization or live reload.
"""

import os
from pathlib import Path
import subprocess
import unittest

from native_harness import run_tests


ROOT = Path(__file__).resolve().parents[2]

BOUNDARIES = r'''
#include <Python.h>
#include <cassert>
#include <iostream>
#include <memory>
#include <string>
#include <utility>
template<class T> using Holder = std::shared_ptr<T>;
enum class GAMVersion { Initial = 0, Override = 22 };
struct Game { GAMVersion version = GAMVersion::Initial; } gameStorage;
struct Sprite2D {};
struct SaveGame {};
template<class T> struct CObject {
    explicit CObject(PyObject* obj) { assert(obj); }
};
static int conversions = 0;
static Holder<Sprite2D> expectedPicture = std::make_shared<Sprite2D>();
static Holder<Sprite2D> SpriteFromPy(PyObject* obj) {
    assert(obj && obj != Py_None);
    assert(PyCapsule_GetPointer(obj, "test.sprite") == expectedPicture.get());
    ++conversions;
    return expectedPicture;
}
static std::string PyString_AsStringObj(PyObject* obj) {
    const char* value = PyUnicode_AsUTF8(obj);
    assert(value);
    return value;
}
static PyObject* RuntimeError(const char* text) {
    PyErr_SetString(PyExc_RuntimeError, text);
    return nullptr;
}
struct SaveGameIterator {
    int slot = -1;
    bool multiple = false;
    int calls = 0;
    std::string description;
    Holder<Sprite2D> picture;
    int CreateSaveGame(int value, bool quicksaves, Holder<Sprite2D> preview) {
        ++calls; slot = value; multiple = quicksaves; picture = std::move(preview);
        return 17;
    }
    int CreateSaveGame(CObject<SaveGame>, std::string name, Holder<Sprite2D> preview) {
        ++calls; description = std::move(name); picture = std::move(preview);
        return 23;
    }
};
struct Core {
    struct { bool MultipleQuickSaves = true; } config;
    Holder<SaveGameIterator> iterator = std::make_shared<SaveGameIterator>();
    const Holder<SaveGameIterator>& GetSaveGameIterator() const { return iterator; }
} coreStorage;
Core* core = &coreStorage;
#define GET_GAME() Game* game = &gameStorage
#define PARSE_ARGS(args, ...) if (!PyArg_ParseTuple(args, __VA_ARGS__)) return nullptr
'''

SCENARIOS = r'''
int main(int argc, char** argv) {
    assert(argc == 2);
    Py_Initialize();
    const std::string scenario = argv[1];
    PyObject* args = nullptr;
    if (scenario == "quick_omitted") {
        args = Py_BuildValue("(i)", 1);
    } else if (scenario == "named_omitted") {
        args = Py_BuildValue("(Os)", Py_None, "Named save");
    } else if (scenario == "named_version") {
        args = Py_BuildValue("(Osi)", Py_None, "Named save", 22);
    } else if (scenario == "named_none") {
        args = Py_BuildValue("(OsiO)", Py_None, "Named save", 22, Py_None);
    } else if (scenario == "named_picture") {
        PyObject* picture = PyCapsule_New(expectedPicture.get(), "test.sprite", nullptr);
        args = Py_BuildValue("(OsiO)", Py_None, "Named save", 22, picture);
        Py_DECREF(picture);
    } else {
        return 2;
    }
    assert(args);
    PyObject* result = GemRB_SaveGame(nullptr, args);
    if (!result) PyErr_Print();
    assert(result && !PyErr_Occurred());
    const auto& saved = core->iterator;
    assert(saved->calls == 1);
    const bool quick = scenario == "quick_omitted";
    assert(PyLong_AsLong(result) == (quick ? 17 : 23));
    assert(saved->slot == (quick ? 1 : -1));
    assert(saved->multiple == quick);
    assert(saved->description == (quick ? "" : "Named save"));
    const bool hasPicture = scenario == "named_picture";
    assert(conversions == (hasPicture ? 1 : 0));
    assert(saved->picture == (hasPicture ? expectedPicture : nullptr));
    const bool hasVersion = !quick && scenario != "named_omitted";
    assert(gameStorage.version == (hasVersion ? GAMVersion::Override : GAMVersion::Initial));
    Py_DECREF(result);
    Py_DECREF(args);
    Py_Finalize();
    std::cout << scenario << " passed\n";
}
'''


def generate_harness():
    source = (ROOT / "plugins/GUIScript/GUIScript.cpp").read_text()
    start = source.index("static PyObject* GemRB_SaveGame(")
    end = source.index("\nPyDoc_STRVAR(", start)
    return BOUNDARIES + source[start:end] + SCENARIOS


class SaveGameTests(unittest.TestCase):
    def scenario(self, name):
        environment = os.environ.copy()
        python_home = environment.pop("GEMRB_TEST_PYTHONHOME", None)
        if python_home:
            environment["PYTHONHOME"] = python_home
        result = subprocess.run([str(self.binary), name], capture_output=True,
                                text=True, timeout=20, env=environment)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(name + " passed", result.stdout)

    def test_quicksave_omitted_preview(self): self.scenario("quick_omitted")
    def test_named_save_omitted_preview(self): self.scenario("named_omitted")
    def test_version_override_omitted_preview(self): self.scenario("named_version")
    def test_explicit_none_preview(self): self.scenario("named_none")
    def test_explicit_preview_reaches_save_storage(self): self.scenario("named_picture")


if __name__ == "__main__":
    run_tests(SaveGameTests, generate_harness)
