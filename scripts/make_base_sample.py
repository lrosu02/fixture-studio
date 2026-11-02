"""Original asymmetric base specimen; dimensions are test inputs, not app defaults."""
from pathlib import Path
import cadquery as cq

def main():
    base=cq.Workplane('XY').box(100,75,8,centered=(True,True,False))
    for x,y in [(-36,-23),(34,-23),(-31,24),(30,19)]:
        base=base.cut(cq.Workplane('XY').center(x,y).circle(1.5).extrude(8))
    cq.exporters.export(base,str(Path(__file__).resolve().parents[1]/'samples'/'mounting_base.step'))

if __name__=='__main__':
    main()
