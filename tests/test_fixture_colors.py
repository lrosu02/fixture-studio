from types import SimpleNamespace

from fixture.planning import compile_plan
from fixture.viewer import assembly_figure, fixture_body_color, SOURCE_COLOR
from tests.test_geometry import ready


def mesh_colors(fig):
    return {trace.name: trace.color for trace in fig.data if trace.type == "mesh3d"}


def test_fixture_parts_have_distinct_stable_colors_and_sources_stay_gray():
    a, r = ready()
    names = ("mounting-platform", "base-foot", "corner-rib-0", "corner-rib-1")
    revision = SimpleNamespace(
        requirements=r, plan=compile_plan(a, r), meshes={name: a.mesh for name in names}
    )
    original = mesh_colors(assembly_figure(a, revision=revision))
    assert len({original[name] for name in names}) == len(names)
    assert original["Source 1"] == SOURCE_COLOR
    assert all(original[name] != SOURCE_COLOR for name in names)
    hidden_source = mesh_colors(assembly_figure(a, revision=revision, source=False))
    assert hidden_source == {name: original[name] for name in names}
    revision.meshes = {name: a.mesh for name in reversed(names)}
    revision.meshes["new-panel"] = a.mesh
    next_revision = mesh_colors(assembly_figure(a, revision=revision, source=False))
    assert all(next_revision[name] == original[name] for name in names)


def test_previous_revision_uses_same_body_identity_colors():
    a, r = ready()
    names = ("stock-0", "stock-1", "stock-0-cap")
    revision = SimpleNamespace(
        requirements=r, plan=compile_plan(a, r), meshes={name: a.mesh for name in names}
    )
    fig = assembly_figure(a, revision=revision, previous=revision)
    colors = mesh_colors(fig)
    assert len({colors[name] for name in names}) == len(names)
    assert all(
        colors["Previous " + name] == colors[name] == fixture_body_color(name)
        for name in names
    )
    assert fig.layout.legend.font.size >= 12
