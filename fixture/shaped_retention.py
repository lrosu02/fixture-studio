"""Bounded convex-envelope nests and analytic cylindrical retention."""
import numpy as np
from .contracts import Operation, Plan, MM_TOL
from .intake import selected_interface, local_points
from .clearance import stable_profile
from .fasteners import fastener_size, standard_size

MODES=('nest','saddle','collar','split_clamp')


def cylinder_dimensions(a,r,i):
    if i.support_kind!='cylinder':
        raise ValueError('Select a measured outside cylindrical face for this retention method.')
    length=r.retention_length or i.support_length/2
    if length>i.support_length+MM_TOL:
        raise ValueError('Retention length exceeds the measured cylindrical face.')
    radius=i.support_radius
    points=local_points(a.mesh.vertices,i)
    facets=points[np.asarray(a.mesh.triangles)]
    facets=facets[(facets[:,:,1].min(axis=1)<=length/2)&(facets[:,:,1].max(axis=1)>=-length/2)]
    clipped=[facets[(abs(facets[:,:,1])<=length/2)]]
    for boundary in (-length/2,length/2):
        for n in range(3):
            u,v=facets[:,n],facets[:,(n+1)%3]
            crossing=(u[:,1]<boundary)!=(v[:,1]<boundary)
            u,v=u[crossing],v[crossing]
            if len(u): clipped.append(u+(v-u)*((boundary-u[:,1])/(v[:,1]-u[:,1]))[:,None])
    pts=np.concatenate(clipped)
    if len(pts) and np.hypot(pts[:,0],pts[:,2]-radius).max()>radius+.2:
        raise ValueError('Other source geometry protrudes beyond the selected cylinder within this support length. Select another cylinder or shorten the support.')
    if r.thickness<r.locating_clearance+1:
        raise ValueError('The saddle/collar needs at least 1 mm of base material below its fit clearance.')
    diameter=0.
    if r.part_attachment=='split_clamp':
        nominal=fastener_size(r.retention_fastener)
        if nominal is None:
            raise ValueError('Choose the split-clamp screw size.')
        diameter=standard_size(nominal,r.clearance_fit)[0]
        if length<diameter+4:
            raise ValueError('Clamp length must leave 2 mm of material beside its bolt holes.')
    return radius,float(length),diameter


def retention_ops(a,r,placements,target):
    i=selected_interface(a,r)
    points=local_points(a.mesh.vertices,i)
    ops=[]
    def emit(**kw):
        ops.append(Operation(provenance={'source':'measured','shape':'derived','fit':'assumed'},**kw))
    for n,p in enumerate(placements):
        p=np.asarray(p)
        name=f'retention-{n}'
        if r.part_attachment=='nest':
            if i.support_kind!='plane' or points[:,2].min() < -MM_TOL:
                raise ValueError('A contour nest requires an outer planar support face.')
            height=r.locating_height or min(5.,float(points[:,2].max()/2))
            outer=stable_profile(points[:,:2],r.locating_clearance+r.locating_wall)
            inner=stable_profile(points[:,:2],r.locating_clearance)
            for label,polygon,z,h,kind in [('outer',outer,-.2,height+.2,'support'),('cavity',inner,0.,height+1,'relief')]:
                lo=polygon.min(axis=0);hi=polygon.max(axis=0)
                emit(id=name+'-'+label,kind=kind,body=name if kind=='support' else None,target=target,shape='prism',origin=tuple(np.r_[lo,z]+p),size=(*tuple(hi-lo),h),profile=tuple(map(tuple,polygon-lo)),purpose='Convex envelope nest '+label)
                if kind=='support': emit(id=name+'-join',kind='combine',target=target,other=name,purpose='Connect nest to base')
            continue
        radius,length,d=cylinder_dimensions(a,r,i)
        inner=radius+r.locating_clearance
        outer=inner+r.locating_wall
        halfwidth=outer+(d+4 if d else 0)
        h=radius-r.split_gap/2 if d else radius
        emit(id=name,kind='support',body=name,target=target,shape='cylinder' if r.part_attachment=='collar' else 'box',axis='y' if r.part_attachment=='collar' else 'z',origin=tuple(p+([0,-length/2,radius] if r.part_attachment=='collar' else [-halfwidth,-length/2,-.2])),size=(outer*2,outer*2,length) if r.part_attachment=='collar' else (halfwidth*2,length,h+.2),purpose='Measured cylindrical retention body')
        emit(id=name+'-join',kind='combine',target=target,other=name,purpose='Connect retention body to base')
        targets=[target]
        if d:
            cap=name+'-cap';targets.append(cap)
            emit(id=cap,kind='stock',body=cap,origin=tuple(p+[-halfwidth,-length/2,radius+r.split_gap/2]),size=(halfwidth*2,length,outer-r.split_gap/2),purpose='Removable split clamp cap')
        for k,body in enumerate(targets):
            emit(id=name+f'-cavity-{k}',kind='relief',target=body,shape='cylinder',axis='y',origin=tuple(p+[0,-length/2-1,radius]),size=(2*inner,2*inner,length+2),purpose='Cylindrical fit envelope')
            if d:
                for side,x in enumerate((-outer-d/2-2,outer+d/2+2)):
                    emit(id=name+f'-bolt-{k}-{side}',kind='relief',target=body,shape='cylinder',origin=tuple(p+[x,0,-r.thickness-1]),size=(d,d,2*radius+r.locating_clearance+r.locating_wall+r.thickness+2),purpose='Split clamp bolt clearance')
    return ops


def compile_retention(a,r,require_ready=True):
    from .planning import _compile_plan, missing_questions
    if r.composition!='plate':
        raise ValueError('Shaped retention currently requires a common base plate.')
    if require_ready and (q:=missing_questions(a,r)):
        raise ValueError('Resolve requirements: '+' '.join(q))
    i=selected_interface(a,r)
    wall=r.locating_wall
    if r.part_attachment!='nest':
        _,_,d=cylinder_dimensions(a,r,i)
        wall+=d+4 if d else 0
    surrogate=r.model_copy(update={'part_attachment':'cradle','locating_wall':wall})
    plan=_compile_plan(a,surrogate,False,8)
    ops=[o for o in plan.operations if not o.id.startswith('locating-wall')]
    ops+=retention_ops(a,r,plan.placements,'stock-0')
    ops=[o.model_copy(update={'depends_on':(ops[n-1].id,) if n else ()}) for n,o in enumerate(ops)]
    return Plan.model_validate({**plan.model_dump(),'version':9,'operations':ops,'parameters':{**plan.parameters,'part_attachment':r.part_attachment,'retention_length_mm':r.retention_length or (i.support_length/2 if i.support_length else 0)}})


def validate_retention(a,r,plan,bodies,add):
    if r.part_attachment not in MODES:
        return
    import usd_brep as sm
    from .executor import primitive
    expected=retention_ops(a,r,plan.placements,'stock-0')
    missing=0.
    for op in expected:
        if op.kind!='relief': continue
        obstruction=sum(abs(sm.booleans.boolean_intersection(b.copy(),primitive(op)).volume()) for b in bodies.values())
        missing=max(missing,obstruction)
    add('Retention clearance','Independent measured nest/cylinder and clamp-bolt sweeps against all fixture solids',missing,'passed' if missing<.01 else 'failed',units='mm³')
    expected_count=1+(len(plan.placements) if r.part_attachment=='split_clamp' else 0)
    add('Retention bodies','One connected base plus one removable cap per split clamp',len(bodies),'passed' if len(bodies)==expected_count else 'failed',units='bodies')
    coverage=0.
    # Verify required shell material independently; access cuts cannot erase walls.
    for op in expected:
        if op.kind not in ('support','stock'): continue
        required=primitive(op)
        for cut in expected:
            if cut.kind=='relief' and (cut.target==op.body or cut.target==op.target):
                required=sm.booleans.boolean_difference(required,primitive(cut))
        volume=abs(required.volume(relative_accuracy=1e-8))
        occupied=sum(abs(sm.booleans.boolean_intersection(b.copy(),required.copy()).volume(relative_accuracy=1e-8)) for b in bodies.values())
        coverage=max(coverage,abs(volume-occupied))
    add('Retention material','Native coverage of the independently derived support/cap after required cavities',coverage,'passed' if coverage<.01 else 'failed',units='mm³')
    add('Retention performance','Fit/installation concept only; load, clamp preload, friction, seating and strength are not solved',r.part_attachment,'not_evaluated',units='relationship')
