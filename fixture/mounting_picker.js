// A component render is an update, not a mount. Keep one scene and one set of
// listeners on its DOM element; Streamlit invokes cleanup only on unmount.
export default function(args) {
    const plot = args.parentElement.querySelector('.mounting-picker-plot');
    if (plot.mountingViewer?.sourceKey !== args.data.source_key) plot.mountingViewer?.dispose();
    if (plot.mountingViewer) {
        plot.mountingViewer.update(args);
        return plot.mountingViewer.dispose;
    }
    const status = args.parentElement.querySelector('.mounting-picker-status');
    const figure = JSON.parse(args.data.figure);
    const meshes = figure.data.filter(t => t.type === 'mesh3d').map(t => ({
        meta:t.meta, ...Object.fromEntries(['x','y','z','i','j','k'].map(k => [k,array(t[k])]))
    }));
    let current = args, context, sequence = 0, face = null, holes = new Set();
    let ready = false, disposed = false, pressed = null, dragged = false;
    let hovered = null, pointer = null, drawPending = false, drawing = false;
    let lastStyle = '';
    const traceStyles = new Map();
    function traceStyle(trace) {
        return JSON.stringify([trace.visible,trace.color,trace.line?.width,trace.marker?.color,trace.marker?.symbol,trace.text]);
    }

    function hint() {
        return current.data.mode === 'holes'
            ? `${holes.size} selected. Click to add; remove with × below. Drag to rotate.`
            : 'Click a mounting surface. Selected holes stay marked. Drag to rotate.';
    }
    function sync(data) {
        if (context !== data.context) {
            context = data.context;
            sequence = data.sequence;
            face = data.interface_id;
            holes = new Set(data.hole_ids);
        } else if (data.sequence >= sequence) {
            sequence = data.sequence;
            face = data.interface_id;
            holes = new Set(data.hole_ids);
        }
        // An older server acknowledgement must never undo a newer local click.
    }
    function style(trace) {
        const m = trace.meta;
        if (!m) return;
        if (m.pick_kind === 'face') {
            trace.visible = current.data.mode === 'face';
            trace.color = m.interface_id === face ? '#ffb454' : '#74a9bc';
        }
        if (m.direction_for) trace.visible = m.direction_for === face;
        if (m.outline_for) trace.visible = m.outline_for === face;
        if (m.hole_id) {
            const selected = m.interface_id === face && holes.has(m.hole_id);
            trace.visible = current.data.mode === 'holes'
                ? !holes.size || m.interface_id === face : selected;
            trace.line.width = selected ? 8 : 5;
            trace.marker.color[trace.marker.color.length - 1] = selected ? '#ffffff' : trace.line.color;
            trace.marker.symbol[trace.marker.symbol.length - 1] = selected ? 'diamond' : 'circle';
            trace.text = trace.text.replace(/Selected ·.*$|Click to select$|Another face ·.*$/,
                selected ? 'Selected · remove using × in the list' : 'Click to select');
        }
    }
    function signature() { return JSON.stringify([current.data.mode,face,[...holes]]); }
    async function redraw() {
        drawPending = true;
        if (!ready || disposed || drawing) return;
        drawing = true;
        try {
            while (drawPending && !disposed) {
                drawPending = false;
                const nextStyle = signature();
                if (nextStyle === lastStyle) continue;
                lastStyle = nextStyle;
                const indices = [], changes = {visible:[], color:[], 'line.width':[], 'marker.color':[], 'marker.symbol':[], text:[]};
                figure.data.forEach((trace,index) => {
                    if (!trace.meta) return; // Never replace or retessellate the source mesh.
                    style(trace);
                    const key = traceStyle(trace);
                    if (traceStyles.get(index) === key) return;
                    traceStyles.set(index,key);
                    indices.push(index);
                    changes.visible.push(trace.visible);
                    changes.color.push(trace.meta.pick_kind === 'face' ? trace.color : undefined);
                    changes['line.width'].push(trace.meta.hole_id ? trace.line.width : undefined);
                    changes['marker.color'].push(trace.meta.hole_id ? [...trace.marker.color] : undefined);
                    changes['marker.symbol'].push(trace.meta.hole_id ? [...trace.marker.symbol] : undefined);
                    changes.text.push(trace.meta.hole_id ? trace.text : undefined);
                });
                if (indices.length) await window.Plotly.restyle(plot, changes, indices);
            }
        } finally { drawing = false; }
    }
    function publish() {
        sequence++;
        // Send immediately. Persistent cumulative state survives a mode switch or
        // a coalesced rerun; each newer event includes every still-selected hole.
        current.setStateValue('picked', {context, sequence, interface_id:face, hole_ids:[...holes]});
        status.textContent = hint();
        redraw();
    }
    function choose(hit) {
        if (!ready || disposed || !hit) return;
        if (current.data.mode === 'holes') {
            if (!hit.hole_id || (holes.size && hit.interface_id !== face)) return;
            if (holes.has(hit.hole_id)) return;
            face = hit.interface_id;
            holes.add(hit.hole_id);
        } else {
            if (face === hit.interface_id) return;
            face = hit.interface_id;
            holes.clear();
        }
        publish();
    }
    function hitAt(x,y) {
        if (current.data.mode === 'holes') {
            return hovered?.pointer && Math.hypot(x-hovered.pointer[0],y-hovered.pointer[1]) <= 12 ? hovered : null;
        }
        const scene = plot._fullLayout?.scene?._scene;
        const params = scene?.glplot?.cameraParams, canvas = scene?.glplot?.canvas;
        if (!params || !canvas) return null;
        const ray = cameraRay(params, scene.dataScale, canvas.getBoundingClientRect(), x,y);
        return ray ? nearestFace(meshes,ray) : null;
    }
    function cancel() { pressed = null; dragged = false; }
    function down(e) {
        cancel();
        if (!ready || e.button !== 0 || e.target.closest?.('.modebar')) return;
        pressed = {point:[e.clientX,e.clientY], hit:hitAt(e.clientX,e.clientY), time:performance.now()};
    }
    function move(e) {
        pointer = [e.clientX,e.clientY];
        if (pressed && Math.hypot(e.clientX-pressed.point[0],e.clientY-pressed.point[1]) > 5) dragged = true;
        if (!plot.contains(e.target)) hovered = null;
    }
    function up(e) {
        const start = pressed;
        pressed = null;
        if (e.button !== 0 || !start || dragged || performance.now()-start.time > 500 ||
            !plot.contains(e.target) || Math.hypot(e.clientX-start.point[0],e.clientY-start.point[1]) > 5) return;
        choose(start.hit || hitAt(e.clientX,e.clientY));
    }
    function hover(event) {
        const hit = event.points?.find(p => p.data?.meta?.hole_id &&
            (!holes.size || p.data.meta.interface_id === face));
        hovered = hit ? {...hit.data.meta, pointer:pointer?.slice()} : null;
    }
    function unhover() { hovered = null; }
    function update(next) {
        if (disposed) return;
        if (next.data.mode !== current.data.mode) { cancel(); hovered = null; }
        current = next;
        sync(next.data);
        status.textContent = hint();
        redraw();
    }
    const resize = new ResizeObserver(() => { if (ready && !disposed) window.Plotly.Plots.resize(plot); });
    function dispose() {
        if (disposed) return;
        disposed = true;
        cancel(); resize.disconnect();
        plot.removeEventListener('pointerdown',down,true);
        window.removeEventListener('pointermove',move,true);
        window.removeEventListener('pointerup',up,true);
        window.removeEventListener('pointercancel',cancel,true);
        window.removeEventListener('blur',cancel);
        if (ready) window.Plotly.purge(plot);
        delete plot.mountingViewer;
    }
    plot.mountingViewer = {sourceKey:args.data.source_key, update, dispose};
    sync(args.data);
    figure.data.forEach(style);
    figure.data.forEach((trace,index) => traceStyles.set(index,traceStyle(trace)));
    lastStyle = signature();
    plot.addEventListener('pointerdown',down,true);
    window.addEventListener('pointermove',move,true);
    window.addEventListener('pointerup',up,true);
    window.addEventListener('pointercancel',cancel,true);
    window.addEventListener('blur',cancel);
    resize.observe(plot);
    window.Plotly.newPlot(plot,figure.data,figure.layout, {responsive:true, displaylogo:false,
        doubleClick:false, modeBarButtonsToRemove:['toImage','sendChartToCloud']}).then(() => {
        if (disposed) { window.Plotly.purge(plot); return; }
        ready = true;
        plot.on('plotly_hover',hover);
        plot.on('plotly_unhover',unhover);
        status.textContent = hint();
        redraw();
    }).catch(() => { if (!disposed) status.textContent = '3D selection could not load. Use the measured lists below.'; });
    return dispose;
}
