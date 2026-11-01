import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

const helpers = (await readFile(new URL('../fixture/face_picker.js',import.meta.url),'utf8')).split('export default function')[0];
const source = await readFile(new URL('../fixture/mounting_picker.js',import.meta.url),'utf8');
const renderer = (await import('data:text/javascript;base64,'+Buffer.from(helpers+source).toString('base64'))).default;
const tick = () => new Promise(resolve => setImmediate(resolve));
class Surface {
    listeners = new Map();
    addEventListener(name,fn) { if (!this.listeners.has(name)) this.listeners.set(name,new Set()); this.listeners.get(name).add(fn); }
    removeEventListener(name,fn) { this.listeners.get(name)?.delete(fn); }
    fire(name,event) { for (const fn of this.listeners.get(name) || []) fn(event); }
    on(name,fn) { this.addEventListener(name,fn); }
    contains(target) { return target === this; }
    closest() { return null; }
    count() { return [...this.listeners.values()].reduce((n,set)=>n+set.size,0); }
}
async function harness({defer=false}={}) {
    const plot = new Surface(), win = new Surface(), status = {}, sent = [], draws = [];
    let creates=0,purges=0,finish;
    const traces = ['a','b','c','d'].map(hole_id=>({
        meta:{interface_id:'face-a',hole_id},line:{color:'#56b4e9',width:5},
        marker:{color:['#56b4e9'],symbol:['circle']},text:'Click to select'
    }));
    traces.push({type:'mesh3d',x:[-1,1,1,-1],y:[-1,-1,1,1],z:[0,0,0,0],i:[0,0],j:[1,2],k:[2,3],meta:{pick_kind:'face',interface_id:'face-a'}});
    win.Plotly = {newPlot:()=>{creates++;return defer?new Promise(resolve=>{finish=resolve;}):Promise.resolve();},
        restyle:async(...args)=>{draws.push(args);}, purge:()=>{purges++;}, Plots:{resize:()=>{}}};
    globalThis.window=win;
    globalThis.ResizeObserver=class {observe(){} disconnect(){}};
    let data={figure:JSON.stringify({data:traces,layout:{scene:{}}}),source_key:'sample',context:'epoch-1',mode:'holes',sequence:0,interface_id:null,hole_ids:[]};
    const parentElement={querySelector:s=>s.includes('status')?status:plot};
    let cleanup;
    function render(updates={}) {
        data={...data,...updates};
        cleanup=renderer({parentElement,data,setStateValue:(_,v)=>sent.push(v)});
    }
    function pointer(type,x=20,y=20,extra={}) {
        (type==='pointerdown'?plot:win).fire(type,{clientX:x,clientY:y,button:0,target:plot,...extra});
    }
    function click(hole='a') {
        pointer('pointermove');
        plot.fire('plotly_hover',{points:[{data:traces.find(t=>t.meta.hole_id===hole)}]});
        pointer('pointerdown');pointer('pointerup');
    }
    render(); await tick();
    return {plot,win,status,sent,draws,render,click,pointer,cleanup:()=>cleanup(),finish:()=>finish(),counts:()=>({creates,purges})};
}

test('rapid clicks and stale acknowledgements keep the complete selection',async()=>{
    const h=await harness();
    h.click('a');h.click('b');
    assert.deepEqual(h.sent.at(-1).hole_ids,['a','b']);
    // Streamlit renders again on the SAME element, without cleanup on updates.
    h.render({sequence:1,interface_id:'face-a',hole_ids:['a']});
    h.click('c');
    assert.deepEqual(h.sent.at(-1).hole_ids,['a','b','c']);
    h.render({sequence:2,interface_id:'face-a',hole_ids:['a','b']});
    h.click('d');h.click('a');
    assert.equal(h.sent.length,4);
    assert.deepEqual(h.sent.at(-1).hole_ids,['a','b','c','d']);
    await tick();
    assert.deepEqual(h.counts(),{creates:1,purges:0});
    assert.equal(h.win.count(),4);
    h.cleanup();assert.equal(h.win.count(),0);
    assert.deepEqual(h.counts(),{creates:1,purges:1});
});

test('face/hole mode switches preserve the scene, camera and unsent acknowledgement state',async()=>{
    const h=await harness();
    const camera={eye:{x:2,y:3,z:1}};
    h.plot._fullLayout={scene:{camera}};
    h.click('a');
    for(let n=0;n<12;n++) {h.render({mode:'face'});h.render({mode:'holes'});}
    h.click('b');await tick();
    assert.equal(h.plot._fullLayout.scene.camera,camera);
    assert.deepEqual(h.sent.at(-1).hole_ids,['a','b']);
    assert.equal(h.sent.length,2);
    assert.deepEqual(h.counts(),{creates:1,purges:0});
    assert.equal(h.win.count(),4);
    h.cleanup();
});

test('explicit removal uses a new epoch and can reselect the removed hole',async()=>{
    const h=await harness();h.click('a');h.click('b');
    h.render({context:'epoch-2',sequence:0,interface_id:'face-a',hole_ids:['a']});
    h.click('b');
    assert.deepEqual(h.sent.at(-1),{context:'epoch-2',sequence:1,interface_id:'face-a',hole_ids:['a','b']});
    h.render({context:'epoch-3',sequence:0,interface_id:'face-a',hole_ids:[]});
    h.click('c');assert.deepEqual(h.sent.at(-1).hole_ids,['c']);
    h.cleanup();
});

test('rotation, cancellation and right clicks cannot change selected holes',async()=>{
    const h=await harness();h.click('a');
    h.pointer('pointerdown');h.pointer('pointermove',60,20);h.pointer('pointerup',60,20);
    h.pointer('pointerdown');h.win.fire('pointercancel',{});h.pointer('pointerup');
    h.pointer('pointerdown',20,20,{button:2});h.pointer('pointerup',20,20,{button:2});
    assert.equal(h.sent.length,1);h.cleanup();
});

test('updates during initial WebGL setup do not create duplicate scenes or handlers',async()=>{
    const h=await harness({defer:true});
    h.render({mode:'face'});h.render({mode:'holes'});h.render({interface_id:'face-a',hole_ids:['a']});
    h.finish();await tick();h.click('b');
    assert.deepEqual(h.sent.at(-1).hole_ids,['a','b']);
    assert.deepEqual(h.counts(),{creates:1,purges:0});
    assert.equal(h.win.count(),4);h.cleanup();
});
