#!/usr/bin/env python3
"""Build AURA's source-backed C4 workspace without importing the application."""
from __future__ import annotations

import argparse
import ast
import hashlib
import http.server
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/architecture/c4"
CACHE = ROOT / "runtime/architecture"
OUTPUT = ROOT / "artifacts/architecture-c4"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def progress(message):
    print(f"Architecture: {message}", file=sys.stderr, flush=True)


def read_json(path):
    return json.loads(path.read_text())


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def source_path(name):
    path = (ROOT / name).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError(f"Source reference is unavailable or outside the repository: {name}")
    return path


def declarations(path):
    """Read syntax, never imports, decorators, model weights or native code."""
    text = path.read_text()
    result = {}
    if path.suffix == '.py':
        for node in ast.parse(text).body:
            if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            members = []
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.Assign) and isinstance(item.value, ast.Constant):
                        members.extend(target.id + ' = ' + str(item.value.value) for target in item.targets if isinstance(target, ast.Name))
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        members.append(item.target.id)
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and not item.name.startswith('_'):
                        args = [a.arg for a in item.args.args if a.arg not in ('self', 'cls')]
                        members.append(item.name + '(' + ', '.join(args) + ')')
            else:
                members = ['(' + ', '.join(a.arg for a in node.args.args) + ')']
            result[node.name] = dict(line=node.lineno, kind='class' if isinstance(node, ast.ClassDef) else 'function', members=members)
    elif path.suffix == '.rs':
        for match in re.finditer(r'^struct (\w+)(?:\([^\n]+\);|\s*\{(.*?)^\})', text, re.M | re.S):
            fields = re.findall(r'^\s+(\w+)\s*:', match[2] or '', re.M)
            result[match[1]] = dict(line=text[:match.start()].count('\n') + 1, kind='struct', members=fields)
    return result


def inspect_sources():
    catalog = read_json(SOURCE / 'source-map.json')
    model = (SOURCE / 'model.dsl').read_text()
    owners = set(re.findall(r'(\w+)\s*=\s*component\s', model))
    actual = {str(p.relative_to(ROOT)) for p in (ROOT / 'src').rglob('*') if p.suffix in ('.py', '.yaml')}
    actual |= {str(p.relative_to(ROOT)) for p in (ROOT / 'native').glob('*/src/**/*.rs')}
    mapped = {}
    for row in catalog['sources']:
        name = row['path']
        source_path(name)
        if name in mapped:
            raise ValueError(f"Duplicate source owner: {name}")
        if row['owner'] not in owners:
            raise ValueError(f"Unknown C3 owner {row['owner']}: {name}")
        if row['classification'] not in ('current', 'retained', 'compatibility', 'evaluation'):
            raise ValueError(f"Unknown source classification: {name}: {row['classification']}")
        mapped[name] = row
    missing, stale = actual - mapped.keys(), mapped.keys() - actual
    if missing or stale:
        raise ValueError(f"Source coverage mismatch: unmapped={sorted(missing)}, stale={sorted(stale)}")
    for view in read_json(SOURCE / 'code/catalog.json'):
        if view['component'] not in owners:
            raise ValueError(f"Unknown code-view component: {view['component']}")
        symbols = set()
        for name, selected in view['symbols'].items():
            if mapped[name]['owner'] != view['component']:
                raise ValueError(f"Code view crosses C3 owner: {view['key']}: {name}")
            found = declarations(source_path(name))
            if set(selected) - found.keys():
                raise ValueError(f"Missing code symbol in {name}: {sorted(set(selected) - found.keys())}")
            symbols.update(selected)
        for left, right, _ in view['edges']:
            if left not in symbols or right not in symbols:
                raise ValueError(f"Unknown code edge in {view['key']}: {left} -> {right}")
    support = []
    for group, prefixes in catalog['supporting_groups'].items():
        for name in prefixes:
            path = ROOT / name
            paths = sorted(p for p in path.rglob('*') if p.is_file() and '__pycache__' not in p.parts) if path.is_dir() else [path]
            support.extend(dict(path=str(p.relative_to(ROOT)), owner=group) for p in paths if p.is_file())
    return dict(status='pass', source_files=len(mapped), sources=list(mapped.values()), supporting_files=support,
                notes=catalog['notes'])


def run(command, name, env=None, timeout=600):
    """Keep diagnostics private; terminate the full temporary process group."""
    log = CACHE / 'logs' / (name + '.log')
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('wb') as stream:
        process = subprocess.Popen([str(c) for c in command], stdout=stream, stderr=subprocess.STDOUT,
                                   env=env, cwd=ROOT, start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        except (KeyboardInterrupt, subprocess.TimeoutExpired):
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise
    if code:
        detail = log.read_text(errors='replace')[-3000:]
        raise RuntimeError(f"{name} failed ({code}); diagnostics: {log.relative_to(ROOT)}\n{detail}")
    return log


def setup(offline=False):
    lock = read_json(SOURCE / 'tools.lock.json')
    downloads = CACHE / 'downloads'
    downloads.mkdir(parents=True, exist_ok=True)
    local_packages = platform.system() == 'Linux' and platform.machine() in ('aarch64', 'arm64')
    wanted = [item for item in lock['downloads'] if local_packages or not item['name'].endswith('.deb')]
    for number, item in enumerate(wanted, 1):
        path = downloads / item['name']
        if not path.exists() or digest(path) != item['sha256']:
            if offline:
                raise RuntimeError(f"Missing verified cached tool: {item['name']}; run setup with network access first")
            progress(f"download {number}/{len(wanted)}: {item['name']}")
            temporary = path.with_suffix(path.suffix + '.partial')
            run(['curl', '--fail', '--location', '--silent', '--show-error', '--retry', '2',
                 '--output', temporary, item['url']], 'download-' + item['name'])
            if digest(temporary) != item['sha256']:
                temporary.unlink()
                raise RuntimeError(f"Checksum mismatch: {item['name']}; cached executable was not replaced")
            temporary.replace(path)
        if item['name'].endswith('.deb'):
            run(['dpkg-deb', '-x', path, CACHE / 'sysroot'], 'extract-' + item['name'])
    if local_packages:
        root = (CACHE / 'sysroot').resolve()
        for path in (root / 'usr/lib/jvm').rglob('*'):
            if path.is_symlink():
                target = os.readlink(path)
                if target.startswith('/etc/java-') and (root / target[1:]).exists():
                    path.unlink()
                    path.symlink_to(root / target[1:])
    java, dot, env = tools()
    if local_packages:
        run([dot, '-c'], 'graphviz-plugins', env)
    versions = {}
    for key, command in [('java', [java, '-version']), ('graphviz', [dot, '-V']),
                         ('structurizr', [java, '-jar', downloads / 'structurizr.war', 'version']),
                         ('plantuml', [java, '-jar', downloads / 'plantuml.jar', '-version'])]:
        log = run(command, key + '-version', env)
        lines = log.read_text().replace(str(ROOT), '$REPO').splitlines()[:4]
        versions[key] = [re.sub(r'^.*? -- ', '', line) for line in lines]
    browser = CACHE / 'browser'
    browser_package = browser / 'node_modules/playwright/package.json'
    if not browser_package.exists() or read_json(browser_package)['version'] != '1.62.0':
        if offline:
            raise RuntimeError('Browser test dependencies are not cached; run setup with network access first')
        if not shutil.which('npm'):
            raise RuntimeError('Architecture browser checks require Node.js 20+ and npm; the AURA runtime is unchanged')
        browser.mkdir(exist_ok=True)
        for name in ('package.json', 'package-lock.json'):
            shutil.copy2(SOURCE / 'browser' / name, browser / name)
        progress('install isolated pinned Playwright browser-test dependency')
        run(['npm', 'ci', '--prefix', browser, '--ignore-scripts', '--no-audit', '--no-fund'], 'browser-setup')
    browser_path = run(['node', '-e', "console.log(require('./runtime/architecture/browser/node_modules/playwright').chromium.executablePath())"], 'browser-path')
    if not Path(browser_path.read_text().strip()).is_file():
        if offline:
            raise RuntimeError('Pinned Chromium is not cached; run setup with network access first')
        progress('install pinned Chromium for architecture rendering')
        run(['node', browser / 'node_modules/playwright/cli.js', 'install', 'chromium'], 'browser-download')
    write_json(CACHE / 'setup-receipt.json', dict(status='pass', versions=versions, tool_lock_sha256=digest(SOURCE / 'tools.lock.json')))
    return dict(status='pass', tools=versions)


def tools():
    java_candidates = list((CACHE / 'sysroot/usr/lib/jvm').glob('*/bin/java'))
    java = os.environ.get('ARCHITECTURE_JAVA') or (str(java_candidates[0]) if java_candidates else shutil.which('java'))
    local_dot = CACHE / 'sysroot/usr/bin/dot'
    dot = os.environ.get('ARCHITECTURE_DOT') or (str(local_dot) if local_dot.exists() else shutil.which('dot'))
    if not java or not dot or not (CACHE / 'downloads/structurizr.war').exists():
        raise RuntimeError('Architecture tools unavailable. Run python3 scripts/architecture.py setup. Other platforms need Java 21+ and Graphviz (ARCHITECTURE_JAVA / ARCHITECTURE_DOT).')
    env = os.environ.copy()
    env['PATH'] = str(Path(dot).parent) + os.pathsep + env.get('PATH', '')
    env['GRAPHVIZ_DOT'] = str(dot)
    if local_dot.exists() and str(dot) == str(local_dot):
        library = CACHE / 'sysroot/usr/lib/aarch64-linux-gnu'
        env['LD_LIBRARY_PATH'] = str(library) + (os.pathsep + env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
        env['GVBINDIR'] = str(library / 'graphviz')
    env['PLAYWRIGHT_SKIP_BROWSER_GC'] = '1'
    return java, dot, env


def generate_code(render=False):
    views = read_json(SOURCE / 'code/catalog.json')
    snippets = []
    java, _, env = tools() if render else (None, None, None)
    for number, view in enumerate(views, 1):
        key = view['key']
        lines = ['@startuml', '!pragma layout smetana', 'skinparam backgroundColor #FFFFFF',
                 'skinparam shadowing false', 'skinparam defaultFontName DejaVu Sans',
                 'skinparam classBackgroundColor #EDF5F3', 'skinparam classBorderColor #42697A',
                 'skinparam ArrowColor #42697A', 'hide empty members', 'title ' + view['title']]
        for name, selected in view['symbols'].items():
            found = declarations(source_path(name))
            for symbol in selected:
                item = found[symbol]
                url = 'https://github.com/JasonLn0711/project_aura/blob/main/' + name + '#L' + str(item['line'])
                lines.append(f'class "{symbol}" as {symbol} <<{item["kind"]}>> [[{url}]] {{')
                lines.extend('  ' + member for member in item['members'][:9])
                lines.append('}')
        lines.extend(f'{left} --> {right} : {label}' for left, right, label in view['edges'])
        lines.append('@enduml')
        target = SOURCE / 'code' / (key + '.puml')
        target.write_text('\n'.join(lines) + '\n')
        snippets.append(f'image {view["component"]} "{key}" {{\n    image "code/{key}.svg"\n    title "{view["title"]}"\n}}')
        if render:
            progress(f"code diagram {number}/{len(views)}: {key}")
            for fmt in ('svg', 'png'):
                run([java, '-Djava.awt.headless=true', '-jar', CACHE / 'downloads/plantuml.jar', '-t' + fmt, target], key + '-' + fmt, env)
    (SOURCE / 'code-views.dsl').write_text('\n'.join(snippets) + '\n')
    return views


def validate_workspace():
    java, _, env = tools()
    run([java, '-jar', CACHE / 'downloads/structurizr.war', 'validate', '-workspace', SOURCE / 'workspace.dsl'], 'validate', env)


def package_output():
    archive = ROOT / 'dist/aura-c4-architecture.zip'
    archive.parent.mkdir(exist_ok=True)
    temporary = archive.with_suffix('.zip.partial')
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(OUTPUT.rglob('*')):
            if path.is_file():
                bundle.write(path, 'aura-c4/' + str(path.relative_to(OUTPUT)))
    temporary.replace(archive)


def check(browser=False):
    coverage = inspect_sources()
    if not (SOURCE / 'code-views.dsl').exists():
        raise RuntimeError('Generated code views are missing; run architecture.py build first')
    validate_workspace()
    manifest_path = OUTPUT / 'manifest.json'
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        stale = [name for name, sha in manifest['application_sources'].items() if digest(source_path(name)) != sha]
        stale += [name for name, sha in manifest['architecture_sources'].items() if digest(source_path(name)) != sha]
        if stale:
            raise RuntimeError(f'Architecture build is stale; run build again: {stale}')
    if browser:
        progress('exercise interactive viewer and every exported view in Chromium')
        run(['node', SOURCE / 'browser/check.cjs'], 'browser-check')
        shutil.copy2(CACHE / 'browser-check.json', OUTPUT / 'browser-validation.json')
        package_output()
    return dict(status='pass', source_files=coverage['source_files'], code_views=len(read_json(SOURCE / 'code/catalog.json')), browser='pass' if browser else 'not_requested')


def build():
    coverage = inspect_sources()
    table = ['# Source ownership map', '', 'Generated from `source-map.json`; one canonical owner per source file.', '',
             '| Source | C3 owner | Classification | Notes |', '| --- | --- | --- | --- |']
    for row in coverage['sources']:
        table.append(f"| [{row['path']}](../../../{row['path']}) | `{row['owner']}` | {row['classification']} | {row['note']} |")
    (SOURCE / 'source-map.md').write_text('\n'.join(table) + '\n')
    views = generate_code(render=True)
    progress('validate Structurizr workspace')
    validate_workspace()
    java, _, env = tools()
    with tempfile.TemporaryDirectory(prefix='build-', dir=CACHE) as temporary:
        stage = Path(temporary)
        site = stage / 'site'
        images = stage / 'images'
        images.mkdir()
        for fmt, directory in [('static', site), ('svg', images), ('png', images), ('json', stage)]:
            progress('export ' + fmt + '; browser rendering may be quiet')
            run([java, '-jar', CACHE / 'downloads/structurizr.war', 'export', '-workspace', SOURCE / 'workspace.dsl',
                 '-format', fmt, '-output', directory], 'export-' + fmt, env)
        # Image views are supplied as pre-rendered code, not reconstructed C4 shapes.
        for view in views:
            for fmt in ('svg', 'png'):
                shutil.copy2(SOURCE / 'code' / (view['key'] + '.' + fmt), images)
        expected = re.findall(r'(?:systemContext|container|component|dynamic|deployment)\s+\w+\s+(?:"[^"]+"\s+)?"([A-Z][\w]+)"\s*\{', (SOURCE / 'views.dsl').read_text())
        expected += [view['key'] for view in views]
        for key in expected:
            for fmt in ('svg', 'png'):
                path = images / (key + '.' + fmt)
                if not path.exists() or path.stat().st_size < 100:
                    raise RuntimeError(f'Missing rendered diagram: {path.name}')
                if fmt == 'svg':
                    ET.parse(path)
                elif path.read_bytes()[:8] != b'\x89PNG\r\n\x1a\n':
                    raise RuntimeError(f'Invalid PNG: {path.name}')
        if not (site / 'index.html').exists():
            raise RuntimeError('Static interactive viewer was not produced')
        catalog = ['# Diagram catalog', '', 'Generated from the Structurizr view inventory. SVG preserves vector text; PNG is ready for slides.', '',
                   '| View | SVG | PNG |', '| --- | --- | --- |']
        for key in expected:
            base = '../../../artifacts/architecture-c4/images/' + key
            catalog.append(f'| `{key}` | [SVG]({base}.svg) | [PNG]({base}.png) |')
        (SOURCE / 'view-catalog.md').write_text('\n'.join(catalog) + '\n')
        OUTPUT.mkdir(parents=True, exist_ok=True)
        for folder in ('images', 'site'):
            if (OUTPUT / folder).exists():
                shutil.rmtree(OUTPUT / folder)
            shutil.copytree(stage / folder, OUTPUT / folder)
        shutil.copy2(stage / 'workspace.json', OUTPUT / 'workspace.json')
        write_json(OUTPUT / 'source-coverage.json', coverage)
        # Exported site deliberately omits documentation. Keep a source-linked guide alongside it.
        sources = {str(p.relative_to(ROOT)): digest(p) for p in SOURCE.rglob('*') if p.is_file() and p.suffix in ('.dsl', '.json', '.puml', '.md', '.cjs', '.svg')}
        sources['scripts/architecture.py'] = digest(Path(__file__))
        source_hashes = {row['path']: digest(ROOT / row['path']) for row in coverage['sources']}
        outputs = {str(p.relative_to(OUTPUT)): digest(p) for p in OUTPUT.rglob('*') if p.is_file() and p.name not in ('manifest.json', 'README.md', 'validation.json')}
        manifest = dict(schema_version=1, status='rendered', source_revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                        view_count=len(expected), view_keys=expected, source_files=coverage['source_files'], code_views=len(views),
                        architecture_sources=sources, application_sources=source_hashes,
                        tool_receipt=read_json(CACHE / 'setup-receipt.json'), output_sha256=outputs,
                        boundary='Architecture rendering and source coverage only; no new ASR or hardware validation.')
        write_json(OUTPUT / 'manifest.json', manifest)
        package_output()
    return dict(status='pass', views=len(expected), source_files=coverage['source_files'], viewer=str((OUTPUT / 'site/index.html').relative_to(ROOT)),
                archive='dist/aura-c4-architecture.zip')


def serve(port=18080):
    if not (OUTPUT / 'site/index.html').exists():
        raise RuntimeError('Interactive viewer unavailable; run architecture.py build first')
    from functools import partial
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(OUTPUT / 'site'))
    with http.server.ThreadingHTTPServer(('127.0.0.1', port), handler) as server:
        progress(f'viewer ready at http://127.0.0.1:{server.server_port}; Ctrl-C stops the foreground server')
        server.serve_forever()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('setup', 'check', 'build', 'serve'))
    parser.add_argument('--json', action='store_true', help='Emit one result object on stdout; progress stays on stderr')
    parser.add_argument('--offline', action='store_true', help='Setup must use verified cached downloads only')
    parser.add_argument('--browser', action='store_true', help='Check every view and navigation using local Chromium')
    parser.add_argument('--port', type=int, default=18080, help='Loopback viewer port (default: 18080)')
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    try:
        progress(args.command + ' started')
        result = setup(args.offline) if args.command == 'setup' else check(args.browser) if args.command == 'check' else build() if args.command == 'build' else serve(args.port)
        if result:
            print(json.dumps(result) if args.json else f"Architecture {args.command}: {result['status']}")
        return 0
    except KeyboardInterrupt:
        if args.command == 'serve':
            progress('viewer stopped')
            return 0
        progress('cancelled; prior published artifacts retained, staging/tools may be resumed')
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        if args.json:
            print(json.dumps(dict(status='failed', error=str(exc))))
        else:
            print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
