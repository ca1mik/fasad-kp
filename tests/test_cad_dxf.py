"""Independent DXF reader checks the CAD export's actual geometry and units."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ezdxf = pytest.importorskip("ezdxf")
ROOT = Path(__file__).resolve().parents[1]


def test_export_opens_in_cad_reader_with_mm_arcs_and_holes(tmp_path: Path) -> None:
    script = """const c=require('./demo/fasad_cad.js');
      const model=c.modelForPart({id:'P',height:700,width:400,thickness:16},
        {template:'rounded_frame',params:{inset:40,bandWidth:8,radius:20,depth:3},
         holes:[{x:100,y:50,radius:3,depth:9}]});
      process.stdout.write(c.dxf(model));"""
    output = subprocess.run(
        ["node", "-e", script], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    path = tmp_path / "roundtrip.dxf"
    path.write_text(output, encoding="utf-8")
    document = ezdxf.readfile(path)
    assert document.units == 4  # DXF millimetres
    assert not document.audit().errors
    entities = list(document.modelspace())
    assert [entity.dxftype() for entity in entities].count("ARC") == 8
    outer = next(entity for entity in entities if entity.dxf.layer == "OUTER")
    assert outer.dxftype() == "LWPOLYLINE"
    assert set(tuple(point[:2]) for point in outer.get_points()) == {
        (0.0, 0.0), (700.0, 0.0), (700.0, 400.0), (0.0, 400.0)
    }
    hole = next(entity for entity in entities if entity.dxf.layer == "HOLES")
    assert (hole.dxf.center.x, hole.dxf.center.y, hole.dxf.radius) == (100.0, 350.0, 3.0)
