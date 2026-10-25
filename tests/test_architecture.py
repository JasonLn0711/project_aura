"""Architecture drift/failure checks use syntax and temporary tool fixtures only."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('aura_architecture', Path(__file__).resolve().parents[1] / 'scripts/architecture.py')
architecture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(architecture)


class ArchitectureTests(unittest.TestCase):
    def fixture(self, root):
        source = root / 'docs/architecture/c4'
        (source / 'code').mkdir(parents=True)
        (root / 'src').mkdir()
        (root / 'src/item.py').write_text("raise RuntimeError('must not import')\nclass Item:\n    def use(self, value): pass\n")
        (source / 'model.dsl').write_text('item = component "Item"\n')
        data = dict(sources=[dict(path='src/item.py', owner='item', classification='current', note='')], supporting_groups={}, notes=[])
        (source / 'source-map.json').write_text(json.dumps(data))
        (source / 'code/catalog.json').write_text(json.dumps([dict(key='Code', component='item', symbols={'src/item.py': ['Item']}, edges=[])]))
        return source

    def test_source_inspection_never_executes_application_code(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = self.fixture(root)
            # Resolved and aliased checkout roots must retain the same boundary.
            for checkout in (root, root / 'src/..'):
                with self.subTest(checkout=checkout), patch.multiple(architecture, ROOT=checkout, SOURCE=source):
                    self.assertEqual(architecture.inspect_sources()['source_files'], 1)

    def test_new_source_requires_explicit_architectural_owner(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = self.fixture(root)
            (root / 'src/new.py').write_text('')
            with patch.multiple(architecture, ROOT=root, SOURCE=source):
                with self.assertRaisesRegex(ValueError, 'unmapped=.*new.py'):
                    architecture.inspect_sources()

    def test_unknown_component_and_stale_code_symbol_fail(self):
        for text, expected in [('unknown', 'Unknown C3 owner'), ('item', 'Missing code symbol')]:
            with self.subTest(text=text), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                source = self.fixture(root)
                data = json.loads((source / 'source-map.json').read_text())
                data['sources'][0]['owner'] = text
                (source / 'source-map.json').write_text(json.dumps(data))
                (root / 'src/item.py').write_text('class Renamed: pass\n')
                with patch.multiple(architecture, ROOT=root, SOURCE=source):
                    with self.assertRaisesRegex(ValueError, expected):
                        architecture.inspect_sources()

    def test_code_view_cannot_silently_cross_component_owner(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = self.fixture(root)
            (source / 'model.dsl').write_text('item = component "Item"\nother = component "Other"\n')
            views = json.loads((source / 'code/catalog.json').read_text())
            views[0]['component'] = 'other'
            (source / 'code/catalog.json').write_text(json.dumps(views))
            with patch.multiple(architecture, ROOT=root, SOURCE=source):
                with self.assertRaisesRegex(ValueError, 'crosses C3 owner'):
                    architecture.inspect_sources()

    def test_source_reference_cannot_escape_repository(self):
        with self.assertRaisesRegex(ValueError, 'outside the repository'):
            architecture.source_path('../planning-everything-track/README.md')

    def test_offline_setup_fails_before_attempting_download(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = self.fixture(root)
            (source / 'tools.lock.json').write_text(json.dumps(dict(downloads=[dict(name='missing.jar', url='https://invalid.example/tool', sha256='0' * 64)])))
            with patch.multiple(architecture, ROOT=root, SOURCE=source, CACHE=root / 'cache'), patch.object(architecture, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'Missing verified cached tool'):
                    architecture.setup(offline=True)
                run.assert_not_called()

    @unittest.skipUnless(os.name == 'posix', 'Architecture tool process-group shutdown targets POSIX hosts')
    def test_quiet_child_timeout_terminates_process(self):
        with tempfile.TemporaryDirectory() as name, patch.object(architecture, 'CACHE', Path(name)):
            with self.assertRaises(subprocess.TimeoutExpired):
                architecture.run([sys.executable, '-c', 'import time; time.sleep(30)'], 'quiet', timeout=.1)

    def test_child_failure_preserves_diagnostics(self):
        with tempfile.TemporaryDirectory() as name, patch.object(architecture, 'CACHE', Path(name)), patch.object(architecture, 'ROOT', Path(name)):
            with self.assertRaisesRegex(RuntimeError, 'fixture failed'):
                architecture.run([sys.executable, '-c', 'import sys; print("fixture failed"); sys.exit(3)'], 'failed')
            self.assertIn('fixture failed', (Path(name) / 'logs/failed.log').read_text())

    def test_json_failure_preserves_stdout_contract(self):
        with patch.object(architecture, 'check', side_effect=RuntimeError('missing fixture')), contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(architecture.main(['check', '--json']), 1)
            self.assertEqual(json.loads(out.getvalue()), dict(status='failed', error='missing fixture'))
            self.assertIn('check started', err.getvalue())

    def test_serve_reports_occupied_port(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / 'site').mkdir()
            (root / 'site/index.html').write_text('fixture')
            with patch.object(architecture, 'OUTPUT', root), patch('http.server.ThreadingHTTPServer', side_effect=OSError('Address already in use')):
                with self.assertRaisesRegex(OSError, 'Address already in use'):
                    architecture.serve()


if __name__ == '__main__':
    unittest.main()
