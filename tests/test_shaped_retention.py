import cadquery as cq
import pytest
from fixture.intake import analyze_file
from fixture.contracts import Requirements
from fixture.project import Project
from fixture.executor import execute
from fixture.validation import validate
from fixture.step_export import prepare_step
from tests.test_retention import ready


@pytest.mark.parametrize('mode',['saddle','collar','split_clamp'])
def test_cylindrical_retention_real_brep_step_and_damage(tmp_path,mode):
    source=tmp_path/'cylinder.step'
    cq.exporters.export(cq.Workplane('XY').circle(10).extrude(40),str(source))
    a=analyze_file(source)
    i=next(i for i in a.interfaces if i.support_kind=='cylinder')
    r=Requirements(purpose='Inspection',quantity=1,interface_id=i.id,mounting_confirmed=True,part_attachment=mode,retention_fastener='M3',surroundings='clamp',fabrication='3D printing',motion_loads='unknown',access='ends open',assumptions_accepted=True)
    p=Project(a,r);rev=p.generate()
    assert rev.metrics['body_count']==(2 if mode=='split_clamp' else 1)
    assert not any(c.result=='failed' for c in rev.checks)
    step=cq.importers.importStep(str(prepare_step(rev))).val()
    assert step.isValid() and len(step.Solids())==rev.metrics['body_count']
    # Independently probe the complete measured cylinder + clearance in exported CAD.
    tool=cq.Solid.makeCylinder(10.45,22,cq.Vector(0,-11,10),cq.Vector(0,1,0))
    assert step.intersect(tool).Volume()<.01
    ops=[o for o in rev.plan.operations if 'cavity' not in o.id]
    damaged=rev.plan.model_copy(update={'operations':tuple(o.model_copy(update={'depends_on':(ops[n-1].id,) if n else ()}) for n,o in enumerate(ops))})
    bodies,_,cuts=execute(damaged,a,tmp_path/'damaged.usda')
    checks=validate(a,r,rev.plan,bodies,cuts)
    assert any(c.result=='failed' and c.name=='Retention clearance' for c in checks)


def test_contour_nest_and_opening_damage(tmp_path):
    a,r=ready();r=r.model_copy(update={'part_attachment':'nest','surroundings':'clamp','bench_hole_count':None})
    rev=Project(a,r).generate()
    assert any(o.shape=='prism' and 'cavity' in o.id for o in rev.plan.operations)
    assert not any(c.result=='failed' for c in rev.checks)
    assert cq.importers.importStep(str(prepare_step(rev))).val().isValid()


def test_cylindrical_retention_rejects_planar_guess():
    a,r=ready()
    with pytest.raises(ValueError,match='cylindrical'):
        Project(a,r.model_copy(update={'part_attachment':'saddle'})).generate()
