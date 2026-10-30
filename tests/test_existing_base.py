import io
import zipfile
import cadquery as cq
import numpy as np
import pytest
from fixture.contracts import BaseMount
from fixture.intake import analyze_file
from fixture.existing_base import measured_positions, transform
from fixture.planning import patch_requirements
from fixture.project import Project
from fixture.step_export import prepare_step
from fixture.viewer import assembly_figure
from tests.test_geometry import ready


def base_requirement():
    a=analyze_file('samples/mounting_base.step')
    i=next(i for i in a.interfaces if i.z[2]<-.99 and len(i.hole_ids)==4)
    return BaseMount(analysis=a,interface_id=i.id,hole_ids=i.hole_ids)


@pytest.mark.parametrize('composition,offset', [('plate',4),('l_bracket',-60)])
def test_measured_base_alignment_step_revision_and_export(tmp_path,composition,offset):
    a,r=ready(composition=composition,base_mount=base_requirement(),surroundings='bolt',bench_fastener='M3',bench_hole_count=4,base_offset_x=3,base_offset_y=offset,base_rotation=17)
    p=Project(a,r)
    rev=p.generate()
    assert not any(c.result=='failed' for c in rev.checks)
    assert rev.metrics['base_hole_count']==4
    solid=cq.importers.importStep(str(prepare_step(rev))).val()
    assert solid.isValid() and len(solid.Solids())==1
    axis=1 if composition=='l_bracket' else 2
    expected=measured_positions(r,rev.plan)
    for point in expected.values():
        # Independent reopened STEP probe, spanning the full bracket base thickness.
        origin=point.copy();origin[axis]-=1
        direction=(0,1,0) if axis==1 else (0,0,1)
        probe=cq.Solid.makeCylinder(1.65,r.thickness+2,cq.Vector(*origin),cq.Vector(*direction))
        assert solid.intersect(probe).Volume()<.01
    figure=assembly_figure(a,revision=rev)
    assert any(t.name=='Existing base' for t in figure.data)
    with zipfile.ZipFile(io.BytesIO(p.export())) as archive:
        assert 'base-analysis.json' in archive.namelist()
        saved=tmp_path/'export.zip';saved.write_bytes(p.export())
    from scripts.reproduce import reproduce
    reproduce(saved,tmp_path/'reproduced')
    changed=p.generate(patch_requirements(r,{'base_offset_x':5}),'Shift relative to base')
    assert changed.parent==rev.id
    p.restore(rev.id)
    assert p.requirements.base_offset_x==3
    reloaded=Project.load(str(__import__('fixture.project',fromlist=['ROOT']).ROOT/'artifacts'/p.id/'project.json'))
    assert reloaded.requirements.base_mount==r.base_mount


def test_base_conflict_preserves_valid_revision():
    a,r=ready(base_mount=base_requirement(),surroundings='bolt',bench_fastener='M3',bench_hole_count=4)
    p=Project(a,r);rev=p.generate()
    with pytest.raises(ValueError,match='count'):
        p.generate(patch_requirements(r,{'bench_hole_count':5}))
    assert p.current==rev
    with pytest.raises(ValueError,match='width'):
        p.generate(patch_requirements(r,{'max_width':65}))
    assert p.current==rev
    with pytest.raises(ValueError,match='locked'):
        patch_requirements(r.model_copy(update={'locks':('base_mount',)}),{'base_mount':None})


def test_base_ui_confirmation_and_application(monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr('fixture.base_controls.picker_component',lambda:lambda **kw:SimpleNamespace(picked=None))
    ui=AppTest.from_file(str(Path('app.py').resolve()),default_timeout=45).run()
    next(b for b in ui.button if b.label=='Load example').click().run()
    next(b for b in ui.button if b.label=='Load synthetic base example').click().run()
    next(s for s in ui.selectbox if s.label=='Base contact face').select(base_requirement().interface_id).run()
    next(c for c in ui.checkbox if c.label.startswith('This base face contacts')).check().run()
    next(b for b in ui.button if b.label=='Use existing base').click().run()
    assert not ui.exception and len(ui.session_state['project'].requirements.base_mount.hole_ids)==4
