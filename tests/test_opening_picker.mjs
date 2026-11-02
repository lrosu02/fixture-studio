import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

const helpers = (await readFile(new URL('../fixture/face_picker.js', import.meta.url), 'utf8')).split('export default function')[0];
const source = await readFile(new URL('../fixture/opening_picker.js', import.meta.url), 'utf8');
const {default: renderer, fixtureHit, openingPreview} = await import('data:text/javascript;base64,' + Buffer.from(helpers + source).toString('base64'));
const tick = () => new Promise(resolve => setImmediate(resolve));
const plane = (z = 0, body = 'wall') => ({body, x: [-1, 1, 1, -1], y: [-1, -1, 1, 1], z: [z, z, z, z], i: [0, 0], j: [1, 2], k: [2, 3]});

test('surface coordinates use the exact nearest ray hit and reference objects occlude', () => {
    const ray = {start: [0.27, 0.13, -3], direction: [0, 0, 6]};
    const hit = fixtureHit([plane(1, 'far'), plane()], ray);
    assert.equal(hit.body, 'wall');
    assert.deepEqual(hit.point, [0.27, 0.13, 0]);
    assert.equal(hit.axis, 'z');
    assert.equal(hit.triangle, 0);
    assert.equal(fixtureHit([plane(), plane(-1, null)], ray), null);
    assert.equal(fixtureHit([plane(), {...plane(-1, null), visible: 'legendonly'}], ray).body, 'wall');
    assert.equal(fixtureHit([plane()], {start: [4, 3, -3], direction: [0, 0, 6]}), null);
    const sloped = {...plane(), z: [-1, 1, 1, -1]};
    assert.equal(fixtureHit([sloped], ray).axis, null);
});

test('diameter preview is in the clicked plane and spans the selected body', () => {
    const mesh = {...plane(), z: [-3, -3, 0, 0]};
    for (const axis of ['x', 'y', 'z']) {
        const draft = {body: 'wall', axis, center: [0.27, 0.13, -1], diameter: 12};
        const shape = openingPreview(draft, [mesh]), k = 'xyz'.indexOf(axis);
        assert.equal(shape.ring.x.length, 65);
        assert.equal(shape.cylinder.x.length, 128);
        assert.equal(shape.cylinder.i.length, 128);
        for (let n = 0; n < 65; n++) {
            const radial = [0, 1, 2].filter(x => x !== k);
            assert.ok(Math.abs(Math.hypot(...radial.map(i => shape.ring['xyz'[i]][n] - draft.center[i])) - 6) < 1e-9);
        }
    }
    assert.equal(openingPreview(null, [mesh]).ring.x.length, 0);
});

class Surface {
    dataset = {};
    listeners = new Map();
    addEventListener(name, fn) { if (!this.listeners.has(name)) this.listeners.set(name, new Set()); this.listeners.get(name).add(fn); }
    removeEventListener(name, fn) { this.listeners.get(name)?.delete(fn); }
    fire(name, event) { for (const fn of this.listeners.get(name) || []) fn(event); }
    contains(target) { return target === this; }
    closest() { return null; }
    count() { return [...this.listeners.values()].reduce((n, set) => n + set.size, 0); }
}
async function harness() {
    const plot = new Surface(), win = new Surface(), sent = [], status = {}, draws = [];
    let creates = 0, reacts = 0, purges = 0;
    const identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
    const camera = {eye: {x: 2, y: 1, z: 2}, up: {x: 0, y: 1, z: 0}};
    plot._fullLayout = {scene: {camera, _scene: {getCamera: () => plot._fullLayout.scene.camera,
        dataScale: [1, 1, 1], glplot: {cameraParams: {projection: identity, view: identity, model: identity},
            canvas: {getBoundingClientRect: () => ({left: 0, top: 0, width: 100, height: 100})}}}}};
    win.Plotly = {
        newPlot: async (p, data, layout) => { creates++; p.data = data; p._fullLayout.scene.camera = layout.scene.camera || camera; },
        react: async (p, data, layout) => { reacts++; p.data = data; p._fullLayout.scene.camera = layout.scene.camera; },
        update: async (p, changes, layout, ids) => {
            draws.push({changes, layout, ids});
            if (layout['scene.camera']) p._fullLayout.scene.camera = layout['scene.camera'];
            for (let n = 0; n < ids.length; n++) for (const [key, values] of Object.entries(changes)) p.data[ids[n]][key] = values[n];
        }, purge: () => {purges++;}, Plots: {resize: () => {}},
    };
    globalThis.window = win;
    globalThis.ResizeObserver = class {observe() {} disconnect() {}};
    const geometry = JSON.stringify({data: [{type: 'mesh3d', ...plane(), meta: {opening_surface: true, opening_body: 'wall'}}], layout: {scene: {camera}}});
    let data = {source_key: 'project', context: 'project:revision1', revision_id: 'revision1', sequence: 0,
        preview: null, diameter: 0.5, enabled: true, geometry_key: 'geometry1', figure: null, geometry_token: null};
    const parentElement = {querySelector: name => name.includes('status') ? status : name.includes('plot') ? plot : null};
    let cleanup;
    function render(updates = {}) {
        data = {...data, ...updates};
        cleanup = renderer({parentElement, data, setStateValue: (name, value) => sent.push({name, value})});
    }
    function pointer(type, x = 64, y = 43, extra = {}) {
        (type === 'pointerdown' ? plot : win).fire(type, {clientX: x, clientY: y, button: 0, pointerId: 1, target: plot, ...extra});
    }
    function click() { pointer('pointerdown'); pointer('pointerup'); }
    render();
    const request = sent.find(x => x.name === 'geometry_request').value;
    render({figure: geometry, geometry_token: request.token}); await tick();
    render({figure: null, geometry_token: null}); await tick();
    return {plot, win, status, sent, draws, geometry, render, pointer, click, cleanup: () => cleanup(), counts: () => ({creates, reacts, purges})};
}

test('clicks, diameter changes and tool switches reuse one scene and preserve live zoom', async () => {
    const h = await harness(), scene = h.plot.dataset.sceneId;
    h.plot._fullLayout.scene.camera.eye = {x: 0.4, y: 0.2, z: 0.7};
    const zoomed = structuredClone(h.plot._fullLayout.scene.camera);
    h.click(); await tick();
    const event = h.sent.find(x => x.name === 'picked').value;
    assert.equal(event.revision_id, 'revision1');
    assert.equal(event.context, 'project:revision1');
    assert.equal(event.sequence, 1);
    assert.ok(Math.abs(event.point[0] - 0.28) < 1e-9);
    assert.ok(Math.abs(event.point[1] - 0.14) < 1e-9);
    h.render({diameter: 1, sequence: 0}); await tick(); // Delayed acknowledgement cannot erase the pick.
    assert.equal(h.plot.dataset.previewDiameter, '1');
    assert.ok(h.plot.data.at(-2).x.length > 0);
    h.render({enabled: false}); await tick();
    assert.equal(h.plot.data.at(-2).x.length, 0);
    h.render({enabled: true}); await tick();
    assert.equal(h.plot.dataset.sceneId, scene);
    assert.ok(Number(h.plot.dataset.updateBytes) < 500);
    assert.deepEqual(h.plot._fullLayout.scene.camera, zoomed);
    assert.deepEqual(h.counts(), {creates: 1, reacts: 0, purges: 0});
    h.cleanup(); assert.equal(h.win.count(), 0);
});

test('drags, cancelled pointers, modebar clicks and disabled mode never place holes', async () => {
    const h = await harness();
    h.pointer('pointerdown'); h.pointer('pointermove', 80, 43); h.pointer('pointermove', 64, 43); h.pointer('pointerup');
    h.pointer('pointerdown'); h.win.fire('pointercancel', {}); h.pointer('pointerup');
    h.pointer('pointerdown'); h.win.fire('blur', {}); h.pointer('pointerup');
    h.pointer('pointerdown'); h.pointer('pointerup', 64, 43, {target: {}});
    h.pointer('pointerdown', 64, 43, {target: {closest: () => true}}); h.pointer('pointerup');
    h.pointer('pointerdown', 64, 43, {isPrimary: false}); h.pointer('pointerup');
    h.pointer('pointerdown'); h.pointer('pointerup', 64, 43, {pointerId: 2});
    h.render({enabled: false}); h.click();
    assert.equal(h.sent.filter(x => x.name === 'picked').length, 0);
    h.render({enabled: true}); h.click();
    assert.equal(h.sent.filter(x => x.name === 'picked').length, 1);
    h.cleanup();
});

test('a new revision requests geometry once and updates the same scene with its camera', async () => {
    const h = await harness(), scene = h.plot.dataset.sceneId;
    h.click(); await tick();
    h.plot._fullLayout.scene.camera.eye = {x: 0.3, y: 0.6, z: 0.8};
    const camera = structuredClone(h.plot._fullLayout.scene.camera);
    h.render({context: 'project:revision2', revision_id: 'revision2', sequence: 0, preview: null, geometry_key: 'geometry2'});
    h.render({diameter: 2});
    const requests = h.sent.filter(x => x.name === 'geometry_request');
    assert.equal(requests.length, 2);
    h.render({figure: h.geometry, geometry_token: requests.at(-1).value.token}); await tick();
    h.render({figure: null, geometry_token: null}); await tick();
    assert.equal(h.plot.dataset.sceneId, scene);
    assert.deepEqual(h.plot._fullLayout.scene.camera, camera);
    assert.deepEqual(h.counts(), {creates: 1, reacts: 1, purges: 0});
    assert.equal(h.plot.dataset.previewDiameter, '');
    h.click();
    assert.equal(h.sent.filter(x => x.name === 'picked').at(-1).value.revision_id, 'revision2');
    h.cleanup();
});
