from uuid import uuid4
from pathlib import Path
import streamlit as st
from .contracts import BaseMount
from .intake import analyze_bytes
from .face_picker import picker_component, picker_geometry
from .face_picking import face_label
from .planning import patch_requirements


def base_controls(p):
    with st.expander('Mount to an existing base',expanded=False):
        st.caption('Upload a base plate, frame or enclosure. Select its contact face and holes; the fixture follows that measured pattern. Base thread/engagement and strength remain separate requirements.')
        upload=st.file_uploader('Base STEP',type=['step','stp'],key='base-upload-'+p.id)
        if upload:
            try:
                a=analyze_bytes(upload.getvalue(),upload.name)
                st.session_state['base-analysis-'+p.id]=a
            except Exception as error:
                st.error(str(error));return
        if st.button('Load synthetic base example'):
            path=Path(__file__).resolve().parents[1]/'samples'/'mounting_base.step'
            st.session_state['base-analysis-'+p.id]=analyze_bytes(path.read_bytes(),path.name)
            st.rerun()
        a=st.session_state.get('base-analysis-'+p.id) or (p.requirements.base_mount.analysis if p.requirements.base_mount else None)
        if a is None:
            return
        st.write(a.source_name)
        key=p.id+a.source_hash
        state=st.session_state.setdefault('base-draft-'+key,{'context':uuid4().hex,'selected':p.requirements.base_mount.interface_id if p.requirements.base_mount and p.requirements.base_mount.analysis.source_hash==a.source_hash else None})
        result=picker_component()(data=dict(figure=picker_geometry(a.source_hash+str(a.version),a),context=state['context'],view_key='base-'+key,interface_id=state['selected'],hint='Select the base surface that contacts the fixture.',selected_hint='Base face selected. Confirm its attachment holes below.'),key='base-picker-'+key,on_picked_change=lambda:None,height=555)
        ids=[None,*[i.id for i in a.interfaces]]
        if result.picked and result.picked.get('context')==state['context'] and result.picked.get('interface_id') in ids:
            state['selected']=result.picked['interface_id']
        labels={i.id:face_label(i) for i in a.interfaces}
        face=st.selectbox('Base contact face',ids,index=ids.index(state['selected']),format_func=lambda v:labels.get(v,'Click or choose a base face'),key='base-face-'+state['context']+str(state['selected']))
        if face is None:
            return
        i=next(i for i in a.interfaces if i.id==face)
        selected=st.multiselect('Base attachment holes',list(i.hole_ids),default=list(i.hole_ids),key='base-holes-'+key+face)
        if not selected:
            st.info('Select existing base holes to define the mating pattern. A base with no holes needs a different attachment method.')
        x=st.number_input('Base in-plane X offset (mm)',-1000.,1000.,float(p.requirements.base_offset_x))
        y=st.number_input('Base in-plane Y offset (mm)',-1000.,1000.,float(p.requirements.base_offset_y))
        angle=st.number_input('Base in-plane rotation (degrees)',-180.,180.,float(p.requirements.base_rotation))
        confirmed=st.checkbox('This base face contacts the fixture and these holes are for its fasteners')
        if st.button('Use existing base',disabled=not(selected and confirmed)):
            try:
                m=BaseMount(analysis=a,interface_id=face,hole_ids=tuple(selected))
                p.requirements=patch_requirements(p.requirements,dict(base_mount=m,base_offset_x=x,base_offset_y=y,base_rotation=angle,surroundings='bolt',bench_hole_count=len(selected)))
                p.messages.append(dict(role='user',content=f'Attach to uploaded base {a.source_name}, measured face {face}, holes {selected}. Preserve its measured pattern; base placement X {x:g}, Y {y:g} mm, rotation {angle:g} degrees.'))
                p.save();st.rerun()
            except ValueError as error:
                st.error(str(error))
        if p.requirements.base_mount and st.button('Remove existing base'):
            try:
                p.requirements=patch_requirements(p.requirements,{'base_mount':None})
                p.save();st.rerun()
            except ValueError as error:
                st.error(str(error))
