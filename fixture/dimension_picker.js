const cameras=new Map();
export default function({parentElement,data,setTriggerValue}) {
    const plot=parentElement.querySelector('.dimension-plot');
    const fig=JSON.parse(data.figure);
    if(cameras.has(data.view_key))fig.layout.scene.camera=cameras.get(data.view_key);
    let disposed=false,ready=false,down=null,dragged=false,allowedUntil=0,hover=null,pointer=null;
    const fieldOf=e=>{const field=e.points?.[0]?.data?.meta?.dimension;return data.fields.includes(field)?field:null;};
    function emit(field){if(field&&data.fields.includes(field)){allowedUntil=0;setTriggerValue('picked',{context:data.context,field});}}
    function start(e){
        allowedUntil=0;dragged=false;
        if(e.button!==0||e.target?.closest?.('.modebar')){down=null;return;}
        const field=hover&&Math.hypot(e.clientX-hover.x,e.clientY-hover.y)<=8?hover.field:null;
        down={x:e.clientX,y:e.clientY,t:performance.now(),field};
    }
    function move(e){pointer={x:e.clientX,y:e.clientY};if(down&&Math.hypot(e.clientX-down.x,e.clientY-down.y)>5)dragged=true;}
    function finish(e){
        const click=down&&!dragged&&e.button===0&&Math.hypot(e.clientX-down.x,e.clientY-down.y)<=5&&performance.now()-down.t<500;
        const field=down?.field;down=null;allowedUntil=click?performance.now()+250:0;
        if(click&&field)emit(field);
    }
    function cancel(){down=null;allowedUntil=0;hover=null;}
    plot.addEventListener('pointerdown',start,true);
    window.addEventListener('pointermove',move,true);window.addEventListener('pointerup',finish,true);window.addEventListener('pointercancel',cancel,true);
    const resize=new ResizeObserver(()=>{if(ready&&!disposed)window.Plotly.Plots.resize(plot);});resize.observe(plot);
    window.Plotly.newPlot(plot,fig.data,fig.layout,{responsive:true,displaylogo:false,doubleClick:false}).then(()=>{
        if(disposed){window.Plotly.purge(plot);return;}ready=true;
        plot.on('plotly_hover',e=>{const field=fieldOf(e);hover=field&&pointer?{field,...pointer}:null;});
        plot.on('plotly_unhover',()=>{hover=null;});
        plot.on('plotly_click',e=>{
            const field=fieldOf(e);
            // Plotly 3D may emit click on mouse-down. Wait for a verified release.
            if(down){if(!dragged)down.field=field;return;}
            if(performance.now()<=allowedUntil)emit(field);
        });
        plot.on('plotly_relayout',e=>{if(e['scene.camera']){if(cameras.size>12)cameras.clear();cameras.set(data.view_key,e['scene.camera']);}});
    });
    return ()=>{disposed=true;resize.disconnect();plot.removeEventListener('pointerdown',start,true);window.removeEventListener('pointermove',move,true);window.removeEventListener('pointerup',finish,true);window.removeEventListener('pointercancel',cancel,true);if(ready)window.Plotly.purge(plot);};
}
