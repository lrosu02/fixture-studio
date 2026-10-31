// Exercise the actual component's pointer handling with a minimal Plotly/DOM adapter.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

const source = await readFile(new URL('../fixture/hole_picker.js', import.meta.url), 'utf8');
const faceSource = await readFile(new URL('../fixture/face_picker.js', import.meta.url), 'utf8');
const pause = () => new Promise(resolve => setTimeout(resolve, 140));
test('dimension labels require a deliberate click, ignore rotation and unknown fields', async()=>{
    const source=await readFile(new URL('../fixture/dimension_picker.js',import.meta.url),'utf8');
    const module=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
    const h=await harness(module,{fields:['thickness']});
    const event=field=>({points:[{data:{meta:{dimension:field}}}]});
    h.plot.fire('plotly_click',event('thickness'));assert.equal(h.sent.length,0);
    h.click();h.plot.fire('plotly_click',event('thickness'));assert.deepEqual(h.sent.at(-1),{context:'draft',field:'thickness'});
    h.pointer('pointerdown');h.pointer('pointermove',50,50);h.pointer('pointerup',50,50);h.plot.fire('plotly_click',event('thickness'));
    h.click();h.plot.fire('plotly_click',event('hole_ids'));assert.equal(h.sent.length,1);
    h.pointer('pointerdown');h.plot.fire('plotly_click',event('thickness'));assert.equal(h.sent.length,1);
    h.pointer('pointerup');assert.equal(h.sent.length,2);
    h.pointer('pointerdown');h.plot.fire('plotly_click',event('thickness'));h.pointer('pointermove',50,50);h.pointer('pointerup',50,50);assert.equal(h.sent.length,2);
    h.pointer('pointermove',20,20);h.plot.fire('plotly_hover',event('thickness'));h.click();assert.equal(h.sent.length,3);
    h.cleanup();assert.equal(h.win.listeners.size,0);
});
class Surface {
    listeners = new Map();
    addEventListener(name, fn) { this.listeners.set(name, fn); }
    removeEventListener(name) { this.listeners.delete(name); }
    fire(name, event) { this.listeners.get(name)?.(event); }
    contains(target) { return target === this; }
    closest() { return null; }
}
async function harness(module, data = {}, faceMode = false) {
    const plot = new Surface();
    const win = new Surface();
    const status = {};
    const sent = [];
    const redraws = [];
    plot.on = (name, fn) => plot.addEventListener(name, fn);
    const traces = [['face-a','a'], ['face-a','b'], ['face-b','c']].map(([iface,hole]) => ({
        meta:faceMode ? {interface_id:iface,pick_kind:'face'} : {interface_id:iface,hole_id:hole}, line:{color:'#56b4e9',width:5},
        marker:{color:['#56b4e9','#56b4e9'],symbol:['circle','circle']}, text:'Click to select',
    }));
    if(faceMode) {
        for(const t of traces) {
            const x=t.meta.interface_id==='face-a'?-1:0;
            Object.assign(t,{type:'mesh3d',x:[x,x+1,x+1,x],y:[-1,-1,1,1],z:[0,0,0,0],i:[0,0],j:[1,2],k:[2,3]});
        }
        const identity=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
        plot._fullLayout={scene:{_scene:{dataScale:[1,1,1],glplot:{cameraParams:{model:identity,view:identity,projection:identity},canvas:{getBoundingClientRect:()=>({left:0,top:0,width:100,height:100})}}}}};
    }
    win.Plotly = {newPlot:async () => {}, restyle:(...args) => {redraws.push(args);}, purge:() => {}, Plots:{resize:() => {}}};
    globalThis.window = win;
    globalThis.ResizeObserver = class {observe() {} disconnect() {}};
    const payload = {figure:JSON.stringify({data:traces,layout:{scene:{}}}),
        view_key:'test',context:'draft',interface_id:null,hole_ids:[],...data};
    const cleanup = module.default({parentElement:{querySelector:s=>s.includes('status') ? status : plot},
        data:payload,setTriggerValue:(_, value)=>sent.push(value)});
    await Promise.resolve();
    function pointer(type,x=20,y=20,extra={}) {
        const event = {clientX:x,clientY:y,button:0,target:plot,...extra};
        (type === 'pointerdown' ? plot : win).fire(type,event);
    }
    function hover(hole='a',x=20,y=20) {
        pointer('pointermove',x,y);
        plot.fire('plotly_hover',{points:[{data:traces.find(t=>faceMode ? t.meta.interface_id===hole : t.meta.hole_id===hole)}]});
    }
    function click(x=20,y=20) {pointer('pointerdown',x,y);pointer('pointerup',x,y);}
    return {plot,win,status,sent,redraws,cleanup,pointer,hover,click};
}
let serial = 0;
test('face clicks replace selection; repeated clicks, drags and cancellations preserve it', async () => {
    const module = await import('data:text/javascript;base64,' + Buffer.from(faceSource).toString('base64'));
    const h = await harness(module, {}, true);
    h.hover('face-a'); h.click();
    assert.deepEqual(h.sent.at(-1), {context:'draft',interface_id:'face-a'});
    h.click();
    assert.equal(h.sent.length,1);
    h.hover('face-b'); h.pointer('pointerdown'); h.pointer('pointermove',70,40); h.pointer('pointerup',70,40);
    h.hover('face-b'); h.pointer('pointerdown'); h.win.fire('pointercancel',{}); h.pointer('pointerup');
    await pause();
    assert.equal(h.sent.length,1);
    h.hover('face-b',70,20); h.click(70,20);
    assert.equal(h.sent.at(-1).interface_id,'face-b');
    h.cleanup();
    const reset = await harness(module,{context:'new-source',interface_id:'face-a'},true);
    reset.hover('face-a'); reset.click();
    await pause();
    assert.deepEqual(reset.sent,[]);
    reset.hover('face-b',70,20); reset.click(70,20);
    assert.deepEqual(reset.sent.at(-1),{context:'new-source',interface_id:'face-b'});
    reset.cleanup();
});
test('surface ray picking obeys depth and rejects hidden faces', async()=>{
    const module=await import('data:text/javascript;base64,'+Buffer.from(faceSource).toString('base64'));
    const triangle=(z,id)=>({x:[-1,1,0],y:[-1,-1,1],z:[z,z,z],i:[0],j:[1],k:[2],meta:id?{pick_kind:'face',interface_id:id}:undefined});
    const ray={start:[0,0,-2],direction:[0,0,4]};
    assert.equal(module.nearestFace([triangle(0,'rear'),triangle(-1,'front')],ray).interface_id,'front');
    assert.equal(module.nearestFace([triangle(0,'rear'),triangle(-1)],ray),null);
    assert.equal(module.nearestFace([triangle(0,'face')],{start:[3,0,-2],direction:[0,0,4]}),null);
    const identity=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
    assert.deepEqual(module.cameraRay({model:identity,view:identity,projection:identity},[2,2,2],{left:10,top:20,width:100,height:100},60,70),{start:[0,0,-.5],direction:[0,0,1]});
});
async function freshModule() {
    return import('data:text/javascript;base64,' + Buffer.from(source).toString('base64') + '#' + serial++);
}

test('repeated clicks are additions, rapid clicks travel as a complete batch', async () => {
    const h = await harness(await freshModule());
    h.hover('a'); h.click(); h.click();
    h.hover('b',60,20); h.click(60,20);
    await pause();
    assert.deepEqual(h.sent.at(-1).hole_ids,['a','b']);
    assert.equal(h.redraws.length,2); // One redraw per actual addition, not per hole.
    const count = h.sent.length;
    h.click(60,20);
    await pause();
    assert.equal(h.sent.length,count);
    assert.match(h.status.textContent,/Already selected/);
    h.cleanup();
});

test('drags, right clicks, cancellation and moving away cannot pick a later hover', async () => {
    const h = await harness(await freshModule());
    h.hover(); h.pointer('pointerdown'); h.pointer('pointermove',70,40); h.pointer('pointerup',70,40);
    h.hover(); h.pointer('pointerdown',20,20,{button:2}); h.pointer('pointerup',20,20,{button:2});
    h.hover(); h.pointer('pointerdown'); h.win.fire('pointercancel',{}); h.pointer('pointerup');
    h.plot.fire('plotly_unhover',{}); h.click(90,90);
    h.hover('b',130,130); // A delayed hover at a new cursor location is not the click target.
    await pause();
    assert.deepEqual(h.sent,[]);
    h.cleanup();
});

test('a pending addition survives a rerender and cannot switch mounting faces', async () => {
    const module = await freshModule();
    const first = await harness(module);
    first.hover('a'); first.click(); first.cleanup(); // Before the debounce flush.
    const second = await harness(module);
    await pause();
    assert.deepEqual(second.sent.at(-1).hole_ids,['a']);
    second.hover('c'); second.click();
    await pause();
    assert.deepEqual(second.sent.at(-1).hole_ids,['a']);
    second.cleanup();
    const reset = await harness(module,{context:'cleared'});
    reset.hover('c'); reset.click();
    await pause();
    assert.equal(reset.sent.at(-1).interface_id,'face-b');
    assert.deepEqual(reset.sent.at(-1).hole_ids,['c']);
    reset.cleanup();
});
