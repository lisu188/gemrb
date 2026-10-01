#!/usr/bin/env python3
"""Exercise inventory initialization against classic and EE control layouts."""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


SCRIPTS = Path(__file__).resolve().parents[2] / 'GUIScripts'


class Control:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda *args: self.calls.append((name, args))


class InventoryStoreTests(unittest.TestCase):
    def test_inventory_initializes_with_native_feedback_control(self):
        tree = ast.parse((SCRIPTS / 'bg2/GUIINV.py').read_text())
        callback = next(node for node in tree.body
                        if isinstance(node, ast.FunctionDef) and node.name == 'InitInventoryWindow')
        defines = {}
        exec((SCRIPTS / 'GUIDefines.py').read_text(), defines)
        for family in ('bgee', 'bg2ee', 'bg2'):
            with self.subTest(family=family):
                feedback_id = 64 if family.endswith('ee') else 0x1000003f
                ids = set(range(1, 76)) - {64}
                ids.update((feedback_id, 0x10000039, 0x1000003a))
                controls = {identity: Control() for identity in ids}
                variables = {}
                namespace = dict(defines,
                    GemRB=SimpleNamespace(GetSlotType=lambda slot: {'Count': 0}, SetVar=variables.__setitem__),
                    GameCheck=SimpleNamespace(IsAnyEE=lambda: family.endswith('ee'), IsBG2EE=lambda: family == 'bg2ee'),
                    InventoryCommon=SimpleNamespace(MouseEnterGround=None, MouseLeaveGround=None, OnAutoEquip=None),
                )
                exec(compile(ast.Module(body=[callback], type_ignores=[]), 'GUIINV.InitInventoryWindow', 'exec'), namespace)
                window = SimpleNamespace(AddAlias=lambda *args: None, GetControl=controls.get)
                namespace['InitInventoryWindow'](window)
                self.assertIn(('AddAlias', ('MsgSys', 1)), controls[feedback_id].calls)
                self.assertEqual(variables['TopIndex'], 0)

    def test_bgee_temple_uses_bg1_purchase_label(self):
        tree = ast.parse((SCRIPTS / 'GUISTORE.py').read_text())
        refs = next(node for node in tree.body if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == 'strrefs' for target in node.targets))
        branch = next(node for node in tree.body if isinstance(node, ast.If)
                      and isinstance(node.test, ast.Call) and isinstance(node.test.func, ast.Attribute)
                      and node.test.func.attr == 'IsIWD1')
        for family, expected in [('bg1', 13703), ('bgee', 13703), ('bg2', 8786), ('bg2ee', 8786)]:
            with self.subTest(family=family):
                namespace = {'GameCheck': SimpleNamespace(IsIWD1=lambda: False, IsPST=lambda: False,
                             IsBG1=lambda: family == 'bg1', IsBGEE=lambda: family == 'bgee')}
                exec(compile(ast.Module(body=[refs, branch], type_ignores=[]), 'GUISTORE.configuration', 'exec'), namespace)
                self.assertEqual(namespace['strrefs']['heal'], expected)


if __name__ == '__main__':
    unittest.main()
