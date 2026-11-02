// Exact ray/triangle coordinates in the generated fixture frame. Reference
// objects occlude fixture picks; transparent preview/compare traces do not.
export function fixtureHit(meshes, ray) {
    let nearest = Infinity, selected = null;
    const [sx, sy, sz] = ray.start, [dx, dy, dz] = ray.direction;
    for (const mesh of meshes) {
        if (mesh.visible === false || mesh.visible === 'legendonly') continue;
        for (let n = 0; n < mesh.i.length; n++) {
            const a = mesh.i[n], b = mesh.j[n], c = mesh.k[n];
            const ux = mesh.x[b] - mesh.x[a], uy = mesh.y[b] - mesh.y[a], uz = mesh.z[b] - mesh.z[a];
            const vx = mesh.x[c] - mesh.x[a], vy = mesh.y[c] - mesh.y[a], vz = mesh.z[c] - mesh.z[a];
            const px = dy * vz - dz * vy, py = dz * vx - dx * vz, pz = dx * vy - dy * vx;
            const det = ux * px + uy * py + uz * pz;
            if (Math.abs(det) < 1e-12) continue;
            const tx = sx - mesh.x[a], ty = sy - mesh.y[a], tz = sz - mesh.z[a];
            const u = (tx * px + ty * py + tz * pz) / det;
            if (u < -1e-9 || u > 1 + 1e-9) continue;
            const qx = ty * uz - tz * uy, qy = tz * ux - tx * uz, qz = tx * uy - ty * ux;
            const v = (dx * qx + dy * qy + dz * qz) / det;
            if (v < -1e-9 || u + v > 1 + 1e-9) continue;
            const distance = (vx * qx + vy * qy + vz * qz) / det;
            if (distance < 0 || distance >= nearest) continue;
            nearest = distance;
            const normal = [uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx];
            const length = Math.hypot(...normal), axis = normal.reduce((best, x, i) => Math.abs(x) > Math.abs(normal[best]) ? i : best, 0);
            selected = mesh.body ? {
                body: mesh.body, triangle: n,
                point: ray.start.map((x, i) => x + distance * ray.direction[i]),
                axis: length && Math.abs(normal[axis]) / length > 1 - 1e-6 ? 'xyz'[axis] : null,
                normal: normal.map(x => x / (length || 1)),
            } : null;
        }
    }
    return selected;
}

export function openingPreview(draft, meshes) {
    const ring = {x: [], y: [], z: []}, cylinder = {x: [], y: [], z: [], i: [], j: [], k: []};
    if (!draft || !['x', 'y', 'z'].includes(draft.axis) || !(draft.diameter > 0)) return {ring, cylinder};
    const mesh = meshes.find(m => m.body === draft.body);
    if (!mesh) return {ring, cylinder};
    const axis = 'xyz'.indexOf(draft.axis), radial = [0, 1, 2].filter(n => n !== axis);
    let low = Infinity, high = -Infinity;
    for (const value of mesh[draft.axis]) { low = Math.min(low, value); high = Math.max(high, value); }
    const normal = draft.normal?.[axis] || (Math.abs(draft.center[axis] - low) < Math.abs(draft.center[axis] - high) ? -1 : 1);
    for (let n = 0; n <= 64; n++) {
        const angle = 2 * Math.PI * n / 64, p = [...draft.center];
        p[radial[0]] += draft.diameter / 2 * Math.cos(angle);
        p[radial[1]] += draft.diameter / 2 * Math.sin(angle);
        p[axis] += normal * 0.06;
        for (let k = 0; k < 3; k++) ring['xyz'[k]].push(p[k]);
    }
    for (const height of [low - 0.1, high + 0.1]) for (let n = 0; n < 64; n++) {
        const p = [...draft.center], angle = 2 * Math.PI * n / 64;
        p[axis] = height;
        p[radial[0]] += draft.diameter / 2 * Math.cos(angle);
        p[radial[1]] += draft.diameter / 2 * Math.sin(angle);
        for (let k = 0; k < 3; k++) cylinder['xyz'[k]].push(p[k]);
    }
    for (let n = 0; n < 64; n++) {
        const next = (n + 1) % 64;
        cylinder.i.push(n, n); cylinder.j.push(next, next + 64); cylinder.k.push(next + 64, n + 64);
    }
    return {ring, cylinder};
}

export default function(args) {
    const plot = args.parentElement.querySelector('.opening-picker-plot');
    if (plot.openingViewer?.sourceKey !== args.data.source_key) plot.openingViewer?.dispose();
    if (plot.openingViewer) { plot.openingViewer.update(args); return plot.openingViewer.dispose; }
    const status = args.parentElement.querySelector('.opening-picker-status');
    const fullscreenButton = args.parentElement.querySelector('.opening-picker-fullscreen');
    const shell = args.parentElement.querySelector('.opening-picker-shell');
    async function fullscreen() {
        try {
            const doc = shell.ownerDocument;
            if (doc.fullscreenElement) await doc.exitFullscreen();
            else await shell.requestFullscreen();
        } catch { status.textContent = 'Fullscreen is unavailable in this browser.'; }
    }
    fullscreenButton?.addEventListener('click', fullscreen);
    plot.dataset.sceneId = crypto.randomUUID();
    let current = args, context = args.data.context, sequence = args.data.sequence || 0;
    let draft = args.data.preview, meshes = [], geometryKey, installedToken, requestedKey;
    let pendingFigure, previewDirty = false, drawing = false, ready = false, disposed = false;
    let pressed = null, dragged = false, ringIndex, cylinderIndex;
    function liveCamera() {
        const scene = plot._fullLayout?.scene;
        return scene?._scene?.getCamera?.() || scene?.camera;
    }
    function hint() {
        if (!ready || geometryKey !== current.data.geometry_key) return 'Loading fixture preview…';
        if (!current.data.enabled) return 'Drag to rotate · scroll to zoom.';
        return draft ? `Preview: Ø ${current.data.diameter} mm. Rebuild below to cut the opening.`
            : 'Click a flat fixture surface. Drag to rotate; curved and sloped surfaces are unsupported.';
    }
    async function draw() {
        if (drawing || disposed) return;
        drawing = true;
        try {
            while (!disposed && (pendingFigure || (previewDirty && ready))) {
                if (pendingFigure) {
                    const next = pendingFigure; pendingFigure = null;
                    if (next.key !== current.data.geometry_key) continue;
                    const figure = JSON.parse(next.figure), camera = liveCamera();
                    meshes = figure.data.flatMap((t, traceIndex) => t.type === 'mesh3d' && t.meta?.opening_surface ? [{
                        body: t.meta.opening_body, traceIndex,
                        ...Object.fromEntries(['x', 'y', 'z', 'i', 'j', 'k'].map(k => [k, array(t[k])]))
                    }] : []);
                    ringIndex = figure.data.length;
                    cylinderIndex = ringIndex + 1;
                    figure.data.push({type: 'scatter3d', x: [], y: [], z: [], mode: 'lines', line: {color: '#ffc768', width: 6},
                        hoverinfo: 'skip', showlegend: false, name: 'Opening preview'});
                    figure.data.push({type: 'mesh3d', x: [], y: [], z: [], i: [], j: [], k: [], color: '#ffc768', opacity: 0.18,
                        hoverinfo: 'skip', showlegend: false, name: 'Through opening preview'});
                    if (camera) figure.layout.scene.camera = JSON.parse(JSON.stringify(camera));
                    const config = {responsive: true, displaylogo: false, doubleClick: false, modeBarButtonsToRemove: ['sendChartToCloud']};
                    if (ready) await window.Plotly.react(plot, figure.data, figure.layout, config);
                    else await window.Plotly.newPlot(plot, figure.data, figure.layout, config);
                    if (disposed) { window.Plotly.purge(plot); return; }
                    ready = true; geometryKey = next.key; installedToken = next.token;
                    plot.dataset.geometryKey = geometryKey;
                    plot.dataset.geometryBytes = String(next.figure.length);
                    current.setStateValue('geometry_loaded', installedToken);
                    previewDirty = true;
                }
                if (previewDirty && ready) {
                    previewDirty = false;
                    const shape = openingPreview(current.data.enabled && draft ? {...draft, diameter: current.data.diameter} : null, meshes);
                    const camera = liveCamera();
                    const layout = camera ? {'scene.camera': JSON.parse(JSON.stringify(camera))} : {};
                    plot.dataset.cameraBeforeRedraw = JSON.stringify(camera || null);
                    await window.Plotly.update(plot, {
                        x: [shape.ring.x, shape.cylinder.x], y: [shape.ring.y, shape.cylinder.y], z: [shape.ring.z, shape.cylinder.z],
                        i: [[], shape.cylinder.i], j: [[], shape.cylinder.j], k: [[], shape.cylinder.k],
                    }, layout, [ringIndex, cylinderIndex]);
                    plot.dataset.cameraAfterRedraw = JSON.stringify(liveCamera() || null);
                    plot.dataset.previewDiameter = draft && current.data.enabled ? String(current.data.diameter) : '';
                }
                status.textContent = hint();
            }
        } catch { if (!disposed) status.textContent = 'Fixture preview could not load. Return to the assembly view and retry.'; }
        finally { drawing = false; }
    }
    function hitAt(x, y) {
        const scene = plot._fullLayout?.scene?._scene, params = scene?.glplot?.cameraParams, canvas = scene?.glplot?.canvas;
        if (!params || !canvas || geometryKey !== current.data.geometry_key) return null;
        const ray = cameraRay(params, scene.dataScale, canvas.getBoundingClientRect(), x, y);
        return ray ? fixtureHit(meshes.map(m => ({...m, visible: plot.data[m.traceIndex].visible})), ray) : null;
    }
    function cancel() { pressed = null; dragged = false; }
    function down(e) {
        cancel();
        if (!ready || !current.data.enabled || e.button !== 0 || e.isPrimary === false || e.target.closest?.('.modebar')) return;
        pressed = {point: [e.clientX, e.clientY], pointer: e.pointerId, time: performance.now(), hit: hitAt(e.clientX, e.clientY)};
    }
    function move(e) {
        if (pressed && Math.hypot(e.clientX - pressed.point[0], e.clientY - pressed.point[1]) > 5) dragged = true;
    }
    function up(e) {
        const start = pressed; pressed = null;
        if (!start || e.button !== 0 || dragged || (start.pointer !== undefined && e.pointerId !== start.pointer) ||
            performance.now() - start.time > 500 || !plot.contains(e.target) ||
            Math.hypot(e.clientX - start.point[0], e.clientY - start.point[1]) > 5) return;
        const hit = start.hit;
        if (!hit) { status.textContent = 'Choose a generated fixture surface. Uploaded parts cannot be cut here.'; return; }
        if (!hit.axis) { status.textContent = 'Choose a flat X, Y or Z facing surface. Curved and sloped surfaces are unsupported.'; return; }
        draft = {body: hit.body, center: hit.point, axis: hit.axis, normal: hit.normal};
        previewDirty = true; draw();
        current.setStateValue('picked', {context, sequence: ++sequence, revision_id: current.data.revision_id,
            body: hit.body, triangle: hit.triangle, point: hit.point});
    }
    function update(next) {
        if (disposed) return;
        if (next.data.context !== context) {
            context = next.data.context; sequence = next.data.sequence || 0; draft = next.data.preview; cancel();
        } else if ((next.data.sequence || 0) >= sequence) {
            sequence = next.data.sequence || 0; draft = next.data.preview;
        }
        if (!next.data.enabled) cancel();
        current = next;
        plot.dataset.updateBytes = String(JSON.stringify(next.data).length);
        if (next.data.figure && next.data.geometry_token !== installedToken) {
            pendingFigure = {figure: next.data.figure, token: next.data.geometry_token, key: next.data.geometry_key};
        } else if (geometryKey !== next.data.geometry_key && requestedKey !== next.data.geometry_key) {
            requestedKey = next.data.geometry_key;
            current.setStateValue('geometry_request', {key: requestedKey, token: crypto.randomUUID()});
        }
        previewDirty = true; status.textContent = hint(); draw();
    }
    const resize = new ResizeObserver(() => { if (ready && !disposed) window.Plotly.Plots.resize(plot); });
    function dispose() {
        if (disposed) return;
        disposed = true; cancel(); resize.disconnect();
        fullscreenButton?.removeEventListener('click', fullscreen);
        plot.removeEventListener('pointerdown', down, true);
        window.removeEventListener('pointermove', move, true); window.removeEventListener('pointerup', up, true);
        window.removeEventListener('pointercancel', cancel, true); window.removeEventListener('blur', cancel);
        if (ready) window.Plotly.purge(plot);
        delete plot.openingViewer;
    }
    plot.openingViewer = {sourceKey: args.data.source_key, update, dispose};
    plot.addEventListener('pointerdown', down, true);
    window.addEventListener('pointermove', move, true); window.addEventListener('pointerup', up, true);
    window.addEventListener('pointercancel', cancel, true); window.addEventListener('blur', cancel);
    resize.observe(plot); update(args);
    return dispose;
}
