/* Exercise the real exported Structurizr viewer, entirely over loopback. */
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const {spawn} = require('node:child_process');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../../../..');
const {chromium} = require(path.join(root, 'runtime/architecture/browser/node_modules/playwright'));
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'artifacts/architecture-c4/manifest.json')));
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

async function main() {
    const probe = net.createServer();
    await new Promise(resolve => probe.listen(0, '127.0.0.1', resolve));
    const port = probe.address().port;
    await new Promise(resolve => probe.close(resolve));
    const server = spawn('python3', ['scripts/architecture.py', 'serve', '--port', String(port)], {cwd: root, stdio: ['ignore', 'ignore', 'pipe']});
    let diagnostic = '';
    server.stderr.on('data', block => { diagnostic = (diagnostic + block).slice(-4000); });
    const origin = `http://127.0.0.1:${port}`;
    let browser;
    const errors = [], externalRequests = [], completed = [];
    const screenshots = path.join(root, 'runtime/architecture/browser-screenshots');
    fs.mkdirSync(screenshots, {recursive: true});
    try {
        let ready = false;
        for (let n = 0; n < 100; n++) {
            if (server.exitCode !== null) throw new Error(diagnostic);
            try { const response = await fetch(origin); if (response.ok) { ready = true; break; } } catch {}
            await wait(100);
        }
        assert(ready, 'Foreground viewer did not become available');
        browser = await chromium.launch({headless: true, args: ['--no-sandbox']});
        const context = await browser.newContext({viewport: {width: 1600, height: 1000}});
        await context.route('**/*', route => {
            const url = route.request().url();
            if (url.startsWith(origin + '/') || url.startsWith('data:')) return route.continue();
            externalRequests.push(url);
            return route.abort();
        });
        const page = await context.newPage();
        page.on('pageerror', error => errors.push(String(error)));
        await page.goto(origin + '/?introduction=false#C1_Context');
        await page.waitForFunction(() => window.structurizr?.scripting?.isDiagramRendered());
        const available = await page.evaluate(() => structurizr.scripting.getViews().map(view => view.key));
        assert.deepEqual([...available].sort(), [...manifest.view_keys].sort());
        for (const key of manifest.view_keys) {
            await page.evaluate(key => { location.hash = key; }, key);
            await page.waitForFunction(key => structurizr.scripting.getViewKey() === key && structurizr.scripting.isDiagramRendered(), key);
            assert(await page.locator('#diagram svg, #diagram img').count() > 0, key + ' has no rendered content');
            await page.screenshot({path: path.join(screenshots, key + '.png')});
            completed.push(key);
        }
        await page.evaluate(() => { location.hash = 'C1_Context'; });
        await page.waitForFunction(() => structurizr.scripting.getViewKey() === 'C1_Context' && structurizr.scripting.isDiagramRendered());
        const before = await page.locator('#diagram').innerHTML();
        await page.evaluate(() => structurizr.diagram.zoomIn());
        await wait(100);
        assert.notEqual(await page.locator('#diagram').innerHTML(), before, 'Zoom did not change the rendered transform');
        await page.evaluate(() => structurizr.diagram.zoomOut());
        // Use the actual rendered software-system element to drill into C2.
        await page.locator('#diagram').getByText('Project AURA', {exact: true}).first().dblclick({force: true});
        await page.waitForSelector('#navigationModal.show');
        await page.selectOption('#navigationList', '#C2_Containers');
        await page.locator('#navigationList').press('Enter');
        await page.waitForFunction(() => structurizr.scripting.getViewKey() === 'C2_Containers');
        await page.keyboard.press('Space');
        await page.waitForSelector('#quickFindModal.show, #navigationModal.show');
        await page.keyboard.press('Escape');
        assert.deepEqual(errors, [], 'Viewer JavaScript errors');
        assert.deepEqual(externalRequests, [], 'Viewer requested nonlocal resources');
        const receipt = {status: 'pass', views_checked: completed.length, view_keys: completed,
            zoom: 'pass', drilldown: 'pass', navigation: 'pass', external_requests: externalRequests,
            javascript_errors: errors, browser: browser.version(), foreground_server_cleanup: 'pending'};
        fs.writeFileSync(path.join(root, 'runtime/architecture/browser-check.json'), JSON.stringify(receipt, null, 2) + '\n');
        console.log(JSON.stringify(receipt));
    } finally {
        if (browser) await browser.close();
        if (server.exitCode === null) server.kill('SIGINT');
        if (server.exitCode === null) await Promise.race([new Promise(resolve => server.once('exit', resolve)), wait(5000)]);
        if (server.exitCode === null) { server.kill('SIGKILL'); throw new Error('Viewer did not stop on interrupt'); }
    }
    const receiptPath = path.join(root, 'runtime/architecture/browser-check.json');
    const receipt = JSON.parse(fs.readFileSync(receiptPath));
    receipt.foreground_server_cleanup = 'pass';
    fs.writeFileSync(receiptPath, JSON.stringify(receipt, null, 2) + '\n');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
