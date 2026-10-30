// Plotly is local; browser updates contain measured IDs only.
const cameras = new Map();
const drafts = new Map();

export default function({parentElement, data, setTriggerValue}) {
    const plot = parentElement.querySelector('.hole-picker-plot');
    const status = parentElement.querySelector('.hole-picker-status');
    const figure = JSON.parse(data.figure);
    const viewKey = data.view_key;
    if (cameras.has(viewKey)) figure.layout.scene.camera = cameras.get(viewKey);
    if (!drafts.has(data.context)) {
        if (drafts.size >= 12) drafts.delete(drafts.keys().next().value);
        drafts.set(data.context, {interfaceId:data.interface_id, holes:new Set(data.hole_ids), dirty:false});
    }
    const draft = drafts.get(data.context);
    for (const h of data.hole_ids) draft.holes.add(h);
    if (!draft.interfaceId) draft.interfaceId = data.interface_id;
    let disposed = false, ready = false, pressed = null, dragged = false;
    let hovered = null, pointer = null, pendingClick = null, pendingSend = null;
    const hint = 'Click to add; repeat clicks keep holes selected. Remove with × in the list. Drag to rotate.';

    function styleTrace(trace) {
        const meta = trace.meta;
        if (!meta?.hole_id) return;
        const selected = meta.interface_id === draft.interfaceId && draft.holes.has(meta.hole_id);
        trace.visible = !draft.holes.size || meta.interface_id === draft.interfaceId;
        trace.line.width = selected ? 8 : 5;
        trace.marker.color[trace.marker.color.length-1] = selected ? '#ffffff' : trace.line.color;
        trace.marker.symbol[trace.marker.symbol.length-1] = selected ? 'diamond' : 'circle';
        trace.text = trace.text.replace(/Selected ·.*$|Click to select$|Another face ·.*$/,
            selected ? 'Selected · remove using × in the list' : 'Click to select');
    }
    figure.data.forEach(styleTrace);

    function flush() {
        if (disposed || !draft.dirty || !draft.holes.size) return;
        draft.dirty = false;
        setTriggerValue('picked', {context:data.context, interface_id:draft.interfaceId,
            hole_ids:[...draft.holes]});
    }
    function add(hit) {
        if (!ready || disposed || !hit) return;
        if (draft.holes.size && hit.interface_id !== draft.interfaceId) return;
        if (draft.holes.has(hit.hole_id)) {
            status.textContent = 'Already selected. Use × in the selected-hole list to remove it.';
            return;
        }
        draft.interfaceId = hit.interface_id;
        draft.holes.add(hit.hole_id);
        draft.dirty = true;
        status.textContent = draft.holes.size + ' selected. ' + hint;
        const indices = [], visible = [], widths = [], colors = [], symbols = [], texts = [];
        figure.data.forEach((trace, n) => {
            if (!trace.meta?.hole_id) return;
            styleTrace(trace);
            indices.push(n); visible.push(trace.visible); widths.push(trace.line.width);
            colors.push(trace.marker.color); symbols.push(trace.marker.symbol); texts.push(trace.text);
        });
        // One WebGL redraw for the whole update, rather than one per detected hole.
        window.Plotly.restyle(plot, {visible, 'line.width':widths,
            'marker.color':colors, 'marker.symbol':symbols, text:texts}, indices);
        // Send cumulative additions so coalesced/replayed updates lose no picks.
        clearTimeout(pendingSend);
        pendingSend = setTimeout(flush, 100);
    }
    function hitAt(x, y) {
        if (!hovered || !hovered.pointer) return null;
        return Math.hypot(x-hovered.pointer[0], y-hovered.pointer[1]) <= 12 ? hovered : null;
    }
    const cancel = () => {
        pressed = null;
        dragged = false;
        clearTimeout(pendingClick);
    };
    const down = event => {
        cancel();
        if (!ready || event.button !== 0 || event.target.closest?.('.modebar')) return;
        pressed = {point:[event.clientX,event.clientY], hit:hitAt(event.clientX,event.clientY), time:performance.now()};
    };
    const move = event => {
        pointer = [event.clientX, event.clientY];
        if (pressed && Math.hypot(pointer[0]-pressed.point[0],pointer[1]-pressed.point[1]) > 5) dragged = true;
        if (!plot.contains(event.target)) hovered = null;
    };
    const up = event => {
        const start = pressed;
        pressed = null;
        if (event.button !== 0 || !start || dragged || performance.now()-start.time > 500 ||
            !plot.contains(event.target) || Math.hypot(event.clientX-start.point[0],event.clientY-start.point[1]) > 5) return;
        // Freeze the pressed target; never toggle a later hover after a drag.
        if (start.hit) { add(start.hit); return; }
        const released = [event.clientX,event.clientY];
        pendingClick = setTimeout(() => {
            if (!disposed && pointer && Math.hypot(pointer[0]-released[0],pointer[1]-released[1]) <= 3)
                add(hitAt(...released));
        }, 60);
    };
    plot.addEventListener('pointerdown', down, true);
    window.addEventListener('pointermove', move, true);
    window.addEventListener('pointerup', up, true);
    window.addEventListener('pointercancel', cancel, true);
    window.addEventListener('blur', cancel);
    const resize = new ResizeObserver(() => { if (ready && !disposed) window.Plotly.Plots.resize(plot); });
    resize.observe(plot);
    window.Plotly.newPlot(plot, figure.data, figure.layout, {responsive:true, displaylogo:false,
        doubleClick:false, modeBarButtonsToRemove:['toImage','sendChartToCloud']}).then(() => {
        if (disposed) { window.Plotly.purge(plot); return; }
        ready = true;
        status.textContent = hint;
        plot.on('plotly_relayout', event => {
            if (event['scene.camera']) {
                if (cameras.size > 12) cameras.delete(cameras.keys().next().value);
                cameras.set(viewKey, event['scene.camera']);
            }
        });
        plot.on('plotly_hover', event => {
            const hit = event.points?.find(p => p.data?.meta?.hole_id &&
                (!draft.holes.size || p.data.meta.interface_id === draft.interfaceId));
            hovered = hit ? {...hit.data.meta, pointer:pointer?.slice()} : null;
        });
        plot.on('plotly_unhover', () => { hovered = null; });
        flush();
    }).catch(() => { if (!disposed) status.textContent = '3D selection could not load. Use the measured-hole list below.'; });
    return () => {
        disposed = true;
        cancel();
        clearTimeout(pendingSend);
        resize.disconnect();
        plot.removeEventListener('pointerdown', down, true);
        window.removeEventListener('pointermove', move, true);
        window.removeEventListener('pointerup', up, true);
        window.removeEventListener('pointercancel', cancel, true);
        window.removeEventListener('blur', cancel);
        if (ready) window.Plotly.purge(plot);
    };
}
