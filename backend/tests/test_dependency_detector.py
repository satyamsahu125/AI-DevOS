import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.workspace.dependency_detector import (
    build_package_json,
    build_requirements_txt,
    detect_node_dependencies,
    detect_python_dependencies,
)


class DetectNodeDependenciesTests(unittest.TestCase):
    def test_finds_require_calls(self) -> None:
        content = "const express = require('express');\nconst { Router } = require('express');"
        self.assertEqual(detect_node_dependencies([content]), ["express"])

    def test_finds_es_import_statements(self) -> None:
        content = "import React from 'react';\nimport { useState } from 'react';"
        self.assertEqual(detect_node_dependencies([content]), ["react"])

    def test_ignores_relative_imports(self) -> None:
        content = "const controller = require('../controllers/task_controller');\nimport App from './App';"
        self.assertEqual(detect_node_dependencies([content]), [])

    def test_scoped_package_keeps_scope(self) -> None:
        content = "import { Slot } from '@radix-ui/react-slot';"
        self.assertEqual(detect_node_dependencies([content]), ["@radix-ui/react-slot"])

    def test_deduplicates_across_files(self) -> None:
        contents = ["const express = require('express');", "const app = require('express');"]
        self.assertEqual(detect_node_dependencies(contents), ["express"])


class DetectPythonDependenciesTests(unittest.TestCase):
    def test_finds_import_statements(self) -> None:
        self.assertEqual(detect_python_dependencies(["import flask\nimport os"]), ["flask"])

    def test_finds_from_import_statements(self) -> None:
        self.assertEqual(detect_python_dependencies(["from flask import Flask"]), ["flask"])

    def test_ignores_stdlib_modules(self) -> None:
        self.assertEqual(detect_python_dependencies(["import json\nimport sys\nimport re"]), [])

    def test_ignores_relative_imports(self) -> None:
        self.assertEqual(detect_python_dependencies(["from .models import Task"]), [])

    def test_takes_top_level_package_from_submodule_import(self) -> None:
        self.assertEqual(detect_python_dependencies(["from sqlalchemy.orm import Session"]), ["sqlalchemy"])


class BuildManifestTests(unittest.TestCase):
    def test_build_package_json_includes_dependencies_and_start_script(self) -> None:
        content = build_package_json("my project", ["express"], ["index.js", "routes/tasks.js"])
        payload = json.loads(content)
        self.assertEqual(payload["dependencies"], {"express": "^4.19.0"})
        self.assertEqual(payload["scripts"]["start"], "node index.js")
        self.assertEqual(payload["name"], "my-project")

    def test_build_requirements_txt_one_per_line(self) -> None:
        self.assertEqual(build_requirements_txt(["fastapi", "requests"]), "fastapi>=0.115.0,<1.0.0\nrequests>=2.31.0,<3.0.0\n")

    def test_build_requirements_txt_empty(self) -> None:
        self.assertEqual(build_requirements_txt([]), "")


if __name__ == "__main__":
    unittest.main()
