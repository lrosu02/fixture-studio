"""Measured access references, resolved again on every build and validation."""

import numpy as np
from .contracts import Operation, Plan
from .intake import get_interface, local_points
from .clearance import rear_regions


def options(a, r):
    interface = get_interface(a, r.interface_id)
    result = {}
    for face in a.interfaces:
        points = local_points(face.face_mesh.vertices if face.face_mesh else face.boundary, interface)
        outward = -np.array([np.dot(face.z, v) for v in (interface.x, interface.y, interface.z)])
        result['face:' + face.id] = dict(label=f'Face {face.face_ref + 1}', points=points, outward=outward, kind='face')
        for h, c, d in zip(face.hole_ids, face.centers, face.diameters):
            world = np.array(face.origin) + np.array(c) @ np.array([face.x, face.y, face.z])
            center = local_points([world], interface)[0]
            result['hole:' + h] = dict(label=f'Opening {h} · Ø{d:g} mm', center=center, diameter=d, outward=outward, kind='hole')
    for op in rear_regions(a, interface, r.rear_clearance):
        result['rear:' + op.id] = dict(label='Measured recess ' + op.id.removeprefix('rear-profile-'), region=op, kind='rear')
    return result


def probes(a, r, plan):
    choices = options(a, r)
    if len({s.feature_id for s in r.access_selections}) != len(r.access_selections):
        raise ValueError('Access features may only be selected once.')
    stocks = [o for o in plan.operations if o.kind in ('stock', 'support')]
    z0 = min(o.origin[2] for o in stocks) - 1
    z1 = max(o.origin[2] + o.size[2] for o in stocks) + 1
    result = []
    for k, s in enumerate(r.access_selections):
        if s.feature_id not in choices:
            raise ValueError('An access feature no longer belongs to this source. Select it again.')
        c = choices[s.feature_id]
        common = dict(id=f'selected-access-{k}', kind='relief', purpose='Selected ' + s.intent + ': ' + s.feature_id,
                      provenance={'feature':'measured','intent':'user','extent':'derived','padding':'user'})
        if c['kind'] == 'rear':
            source = rear_regions(a, get_interface(a, r.interface_id), s.padding)
            op = next(o for o in source if 'rear:' + o.id == s.feature_id)
            low = min(z0, op.origin[2]) if s.intent == 'through' else op.origin[2] - s.reach
            op = op.model_copy(update={**common, 'origin':(*op.origin[:2],low), 'size':(*op.size[:2], max(z1, 0)-low)})
        elif c['kind'] == 'hole':
            if abs(c['outward'][2]) < .999:
                raise ValueError('Opening cuts currently require a hole parallel to the mounting normal. Select its face for a finite keep-clear box.')
            lo = z0 if s.intent == 'through' else c['center'][2] - s.reach
            hi = z1 if s.intent == 'through' else c['center'][2] + s.reach
            d = c['diameter'] + 2*s.padding
            op = Operation(**common, shape='cylinder', origin=(*c['center'][:2],lo), size=(d,d,hi-lo))
        else:
            pts = c['points']
            if s.intent == 'through' and abs(c['outward'][2]) < .999:
                raise ValueError('Through cuts follow the mounting normal. Choose a parallel face/opening, or use keep-clear for a side face.')
            if s.intent == 'keep_clear':
                pts = np.concatenate([pts, pts + c['outward']*s.reach])
            low, high = pts.min(axis=0)-s.padding, pts.max(axis=0)+s.padding
            if s.intent == 'through':
                low[2], high[2] = z0, z1
            op = Operation(**common, origin=tuple(low), size=tuple(high-low))
        for n, p in enumerate(plan.placements):
            result.append(op.model_copy(update={'id':op.id+f'-{n}', 'origin':tuple(np.array(op.origin)+p)}))
    return result


def add_access(a, r, plan):
    if not r.access_selections:
        return plan
    ops = list(plan.operations)
    bodies = set()
    for o in ops:
        if o.kind in ('stock','support'):
            bodies.add(o.body)
        if o.kind == 'combine':
            bodies.remove(o.other)
    for probe in probes(a, r, plan):
        for body in sorted(bodies):
            ops.append(probe.model_copy(update={'id':probe.id+'-'+body, 'target':body, 'depends_on':(ops[-1].id,)}))
    return Plan.model_validate({**plan.model_dump(), 'operations':ops})


def validate_access(a, r, plan, bodies, add):
    if not r.access_selections:
        return
    import usd_brep as sm
    from .executor import primitive
    for probe in probes(a, r, plan):
        volume = sum(abs(sm.booleans.boolean_intersection(b.copy(), primitive(probe)).volume()) for b in bodies.values())
        add('Selected access: '+probe.id, 'Independent full-depth or finite measured-feature sweep against native fixture material',
            volume, 'passed' if volume < .01 else 'failed', units='mm³', correction='Preserve the selected access sweep through the completed fixture.')
