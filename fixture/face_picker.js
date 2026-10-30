// Pick only measured face IDs. Dragging never changes the selected face.
const cameras = new Map();
const drafts = new Map();
// Plotly hover snaps to mesh vertices and can report an occluded surface.
// Ray-test the displayed triangles instead, including the source as an occluder.
function array(values) {
    if (!values?.bdata) return values;
    const bytes=Uint8Array.from(atob(values.bdata),c=>c.charCodeAt(0));
    const types={f8:Float64Array,f4:Float32Array,i4:Int32Array,u4:Uint32Array,i2:Int16Array,u2:Uint16Array,i1:Int8Array,u1:Uint8Array};
    return new types[values.dtype](bytes.buffer);
}
function product(a,b) {
    const result=new Array(16).fill(0);
    for(let c=0;c<4;c++)for(let r=0;r<4;r++)for(let k=0;k<4;k++)result[c*4+r]+=a[k*4+r]*b[c*4+k];
    return result;
}
function inverse(a) {
    const rows=Array.from({length:4},(_,r)=>[...Array.from({length:4},(_,c)=>a[c*4+r]),...Array.from({length:4},(_,c)=>+(r===c))]);
    for(let c=0;c<4;c++) {
        let p=c;for(let r=c+1;r<4;r++)if(Math.abs(rows[r][c])>Math.abs(rows[p][c]))p=r;
        if(Math.abs(rows[p][c])<1e-15)return null;
        [rows[c],rows[p]]=[rows[p],rows[c]];
        const scale=rows[c][c];rows[c]=rows[c].map(v=>v/scale);
        for(let r=0;r<4;r++)if(r!==c){const f=rows[r][c];rows[r]=rows[r].map((v,k)=>v-f*rows[c][k]);}
    }
    return Array.from({length:16},(_,n)=>rows[n%4][4+Math.floor(n/4)]);
}
export function cameraRay(params,scale,rect,x,y) {
    const matrix=inverse(product(params.projection,product(params.view,params.model)));
    if(!matrix || !rect.width || !rect.height)return null;
    function point(z) {
        const clip=[2*(x-rect.left)/rect.width-1,1-2*(y-rect.top)/rect.height,z,1];
        const out=Array.from({length:4},(_,r)=>clip.reduce((s,v,c)=>s+v*matrix[c*4+r],0));
        return out.slice(0,3).map((v,n)=>v/out[3]/scale[n]);
    }
    const start=point(-1),end=point(1);
    return {start,direction:end.map((v,n)=>v-start[n])};
}
export function nearestFace(meshes,ray) {
    let nearest=Infinity,selected=null;
    const [sx,sy,sz]=ray.start,[dx,dy,dz]=ray.direction;
    for(const m of meshes) {
        // Moller-Trumbore, without allocating arrays for every source triangle.
        for(let n=0;n<m.i.length;n++) {
            const a=m.i[n],b=m.j[n],c=m.k[n];
            const e1x=m.x[b]-m.x[a],e1y=m.y[b]-m.y[a],e1z=m.z[b]-m.z[a];
            const e2x=m.x[c]-m.x[a],e2y=m.y[c]-m.y[a],e2z=m.z[c]-m.z[a];
            const px=dy*e2z-dz*e2y,py=dz*e2x-dx*e2z,pz=dx*e2y-dy*e2x;
            const det=e1x*px+e1y*py+e1z*pz;
            if(Math.abs(det)<1e-12)continue;
            const tx=sx-m.x[a],ty=sy-m.y[a],tz=sz-m.z[a];
            const u=(tx*px+ty*py+tz*pz)/det;
            if(u<0 || u>1)continue;
            const qx=ty*e1z-tz*e1y,qy=tz*e1x-tx*e1z,qz=tx*e1y-ty*e1x;
            const v=(dx*qx+dy*qy+dz*qz)/det;
            if(v<0 || u+v>1)continue;
            const distance=(e2x*qx+e2y*qy+e2z*qz)/det;
            if(distance>=0 && distance<nearest) {nearest=distance;selected=m.meta?.pick_kind==='face'?m.meta:null;}
        }
    }
    return selected;
}
export default function({parentElement, data, setTriggerValue}) {
    const plot = parentElement.querySelector('.face-picker-plot');
    const status = parentElement.querySelector('.face-picker-status');
    const figure = JSON.parse(data.figure);
    const meshes=figure.data.filter(t=>t.type==='mesh3d').map(t=>({meta:t.meta,...Object.fromEntries(['x','y','z','i','j','k'].map(k=>[k,array(t[k])]))}));
    if (cameras.has(data.view_key)) figure.layout.scene.camera = cameras.get(data.view_key);
    if (!drafts.has(data.context)) {
        if (drafts.size >= 12) drafts.delete(drafts.keys().next().value);
        drafts.set(data.context, {id:data.interface_id, dirty:false});
    }
    const draft = drafts.get(data.context);
    let disposed=false, ready=false, pressed=null, dragged=false;
    const hint=data.hint || 'Click a flat mounting surface. Orange arrow shows the fixture side. Drag to rotate.';
    function style(trace) {
        if (trace.meta?.pick_kind === 'face') trace.color = trace.meta.interface_id === draft.id ? '#ffb454' : '#74a9bc';
        if (trace.meta?.direction_for) trace.visible = trace.meta.direction_for === draft.id;
    }
    figure.data.forEach(style);
    function flush() {
        if (draft.dirty && draft.id && !disposed) {
            draft.dirty=false;
            setTriggerValue('picked',{context:data.context,interface_id:draft.id});
        }
    }
    function choose(hit) {
        if (!ready || disposed || !hit || draft.id === hit.interface_id) return;
        draft.id=hit.interface_id; draft.dirty=true;
        const ids=[], colors=[], directions=[], visibility=[];
        figure.data.forEach((trace,n)=>{
            if (!trace.meta) return;
            style(trace);
            if (trace.meta.pick_kind==='face') {ids.push(n);colors.push(trace.color);}
            if (trace.meta.direction_for) {directions.push(n);visibility.push(trace.visible);}
        });
        window.Plotly.restyle(plot,{color:colors},ids);
        window.Plotly.restyle(plot,{visible:visibility},directions);
        status.textContent=data.selected_hint || 'Mounting face selected. Review its holes below, then apply. Drag to rotate.';
        flush();
    }
    function hitAt(x,y) {
        const scene=plot._fullLayout?.scene?._scene;
        const params=scene?.glplot?.cameraParams,canvas=scene?.glplot?.canvas;
        if(!params || !canvas) return null;
        const ray=cameraRay(params,scene.dataScale,canvas.getBoundingClientRect(),x,y);
        return ray?nearestFace(meshes,ray):null;
    }
    function cancel() {pressed=null;dragged=false;}
    function down(e) {
        cancel();
        if (!ready || e.button!==0 || e.target.closest?.('.modebar')) return;
        pressed={point:[e.clientX,e.clientY],time:performance.now()};
    }
    function move(e) {
        if (pressed && Math.hypot(e.clientX-pressed.point[0],e.clientY-pressed.point[1])>5) dragged=true;
    }
    function up(e) {
        const start=pressed;pressed=null;
        if (e.button!==0 || !start || dragged || performance.now()-start.time>500 || !plot.contains(e.target) || Math.hypot(e.clientX-start.point[0],e.clientY-start.point[1])>5) return;
        choose(hitAt(e.clientX,e.clientY));
    }
    plot.addEventListener('pointerdown',down,true);
    window.addEventListener('pointermove',move,true);
    window.addEventListener('pointerup',up,true);
    window.addEventListener('pointercancel',cancel,true);
    window.addEventListener('blur',cancel);
    const resize=new ResizeObserver(()=>{if (ready && !disposed) window.Plotly.Plots.resize(plot);});resize.observe(plot);
    window.Plotly.newPlot(plot,figure.data,figure.layout,{responsive:true,displaylogo:false,doubleClick:false,modeBarButtonsToRemove:['toImage','sendChartToCloud']}).then(()=>{
        if (disposed) {window.Plotly.purge(plot);return;}
        ready=true;status.textContent=hint;
        plot.on('plotly_relayout',e=>{
            if (e['scene.camera']) {if(cameras.size>12)cameras.delete(cameras.keys().next().value);cameras.set(data.view_key,e['scene.camera']);}
        });
        flush();
    }).catch(()=>{if(!disposed)status.textContent='Face preview could not load. Choose a measured mounting face from the list below.';});
    return ()=>{
        disposed=true;cancel();resize.disconnect();plot.removeEventListener('pointerdown',down,true);
        window.removeEventListener('pointermove',move,true);window.removeEventListener('pointerup',up,true);
        window.removeEventListener('pointercancel',cancel,true);window.removeEventListener('blur',cancel);
        if(ready)window.Plotly.purge(plot);
    };
}
