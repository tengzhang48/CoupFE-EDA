"""Synthetic stacked-memory package CAD -> conformal Tet4 mesh (Gmsh/OpenCascade).

Run with a Python that provides ``gmsh``. Geometry is built in mm; the solver
arrays are written in m. The package is project-authored and illustrative: a
board with a 7 x 7 ball grid, substrate, interposer, an 8 W logic die, four
four-high memory stacks (0.5 W per die), encapsulation, a top thermal
interface (TIM) and a copper lid -- 90 CAD bodies and 7 materials. It is not a
product stackup.

After meshing, an explicit tetrahedral optimizer pass runs (``--optimizer
netgen`` by default; ``hxt`` switches Mesh.Algorithm3D to 10; ``none`` keeps
Gmsh's native pass only) and a quality audit (Gmsh minSICN plus a NumPy
gamma / edge-conditioning measure) is written to quality.json and embedded in
geometry.json. Without the Netgen pass the 0.45 mm mesh keeps one nearly
coplanar sliver in a die-attach layer that produces a spurious local strain;
nothing is deleted or remeshed selectively, the optimizer either removes it or
the audit reports that it did not.

Meshing uses one thread by default (``--threads``) so that a rebuild with the
same Gmsh version reproduces the same mesh, which ``run.py --check`` relies on.
"""
from pathlib import Path
import argparse
import hashlib
import itertools
import json
import time
import gmsh
import numpy as np


def quality_audit(points, cells, rid, objects, gmsh_min_sicn=None):
    """Per-element shape measures on the exact array the solvers consume."""
    pt = points[cells]
    edge = pt[:, 1:] - pt[:, 0, None]
    volumes = np.linalg.det(edge) / 6
    l2 = np.zeros(len(cells))
    for i, j in itertools.combinations(range(4), 2):
        l2 += np.sum((pt[:, i] - pt[:, j]) ** 2, axis=1)
    # gamma = 12*(3V)^(2/3)/sum(L^2): 1 for a regular tet, ->0 for a sliver.
    gamma = 12 * (3 * volumes) ** (2 / 3) / l2
    condition = np.linalg.cond(edge)
    materials = np.array([o["material"] for o in objects])[rid]
    worst = np.argsort(gamma)[:20]
    audit = dict(
        elements=len(cells),
        min_gamma=float(gamma.min()),
        min_volume_mm3=float(volumes.min()),
        max_edge_condition=float(condition.max()),
        gamma_below=[dict(threshold=t, count=int((gamma < t).sum()))
                     for t in (1e-4, 1e-3, 1e-2, .05, .1, .2)],
        per_material={m: dict(elements=int((materials == m).sum()),
                              min_gamma=float(gamma[materials == m].min()),
                              min_volume_mm3=float(volumes[materials == m].min()),
                              max_edge_condition=float(condition[materials == m].max()))
                      for m in sorted(set(materials))},
        worst_elements=[dict(element=int(e), body=objects[rid[e]]["id"],
                             material=objects[rid[e]]["material"],
                             gamma=float(gamma[e]), volume_mm3=float(volumes[e]),
                             edge_condition=float(condition[e]),
                             centroid_mm=pt[e].mean(axis=0).tolist())
                        for e in worst],
    )
    if gmsh_min_sicn is not None:
        sicn = np.asarray(gmsh_min_sicn)
        audit["min_sicn"] = float(sicn.min())
        audit["sicn_below"] = [dict(threshold=t, count=int((sicn < t).sum()))
                               for t in (1e-4, 1e-3, 1e-2, .05, .1, .2)]
        audit["per_material_min_sicn"] = {m: float(sicn[materials == m].min())
                                          for m in sorted(set(materials))}
    return audit, gamma, condition


def build(out: Path, h: float, optimizer: str = "netgen", threads: int = 1):
    out.mkdir(parents=True, exist_ok=False)
    started = time.time()
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1)
    gmsh.option.setNumber("General.NumThreads", threads)
    gmsh.model.add("stacked_memory_package")
    occ = gmsh.model.occ
    objects = []

    def record(name, tag, material, power=0.):
        objects.append(dict(id=name, original_tags=[tag], material=material, power_W=power))
        return tag

    def box(name, x, y, z, dx, dy, dz, material, power=0.):
        return record(name, occ.addBox(x, y, z, dx, dy, dz), material, power)

    box("board", -11, -11, -1.0, 22, 22, .56, "organic")
    for i, x in enumerate(np.arange(-6., 6.1, 2.)):
        for j, y in enumerate(np.arange(-6., 6.1, 2.)):
            sphere = occ.addSphere(x, y, -.22, .30)
            trim = occ.addBox(x-.4, y-.4, -.44, .8, .8, .44)
            intersect, _ = occ.intersect([(3,sphere)], [(3,trim)])
            assert len(intersect) == 1
            record(f"bga.{i}.{j}", intersect[0][1], "solder")
    box("substrate", -9,-9,0,18,18,.7,"organic")
    box("interposer_attach",-8,-8,.7,16,16,.1,"attach")
    box("interposer",-8,-8,.8,16,16,.25,"silicon")
    mold_tools=[]
    mold_tools.append(box("logic.attach",-3,-3,1.05,6,6,.05,"attach"))
    mold_tools.append(box("logic.die",-3,-3,1.10,6,6,.75,"silicon",8.))
    centers=[(-5.5,-5.5),(5.5,-5.5),(-5.5,5.5),(5.5,5.5)]
    for s,(x,y) in enumerate(centers):
        for d in range(4):
            z=1.05+.2*d
            mold_tools.append(box(f"memory.stack_{s}.attach_{d}",x-2,y-2,z,4,4,.05,"attach"))
            mold_tools.append(box(f"memory.stack_{s}.die_{d}",x-2,y-2,z+.05,4,4,.15,"silicon",.5))
    mold=occ.addBox(-8,-8,1.05,16,16,.8)
    cut,_=occ.cut([(3,mold)],[(3,t) for t in mold_tools],removeObject=True,removeTool=False)
    assert len(cut)==1
    record("encapsulation",cut[0][1],"mold")
    box("top_tim",-8,-8,1.85,16,16,.15,"top_tim")
    box("copper_lid",-9,-9,2.0,18,18,.7,"copper")
    vols=[(3,o["original_tags"][0]) for o in objects]
    _,mapping=occ.fragment(vols[:1],vols[1:])
    occ.synchronize()
    all_volume_tags=[]
    for i,(o,m) in enumerate(zip(objects,mapping)):
        tags=[tag for dim,tag in m if dim==3]
        if not tags: raise RuntimeError(f"lost CAD body {o['id']}")
        o["volume_tags"]=tags
        o["cad_volume_mm3"]=sum(occ.getMass(3,t) for t in tags)
        o["physical_group"]=gmsh.model.addPhysicalGroup(3,tags,tag=i+1)
        gmsh.model.setPhysicalName(3,i+1,o["id"])
        all_volume_tags.extend(tags)
    if len(set(all_volume_tags)) != len(all_volume_tags):
        raise RuntimeError("overlapping material ownership")
    gmsh.write(str(out/"package.step"))
    gmsh.option.setNumber("Mesh.MeshSizeMin",h*.25)
    gmsh.option.setNumber("Mesh.MeshSizeMax",h)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature",14)
    gmsh.option.setNumber("Mesh.ElementOrder",1)
    gmsh.option.setNumber("Mesh.Algorithm3D",10 if optimizer=="hxt" else 1)
    gmsh.option.setNumber("Mesh.Optimize",1)
    # Gmsh's Netgen shape optimizer runs after the native pass; it removes the
    # near-coplanar slivers the native optimizer keeps (they have positive
    # volume, so the native pass sees nothing to fix).
    gmsh.option.setNumber("Mesh.OptimizeNetgen",1 if optimizer=="netgen" else 0)
    gmsh.model.mesh.generate(3)
    gmsh.write(str(out/"package.msh"))
    node_tags,flat,_=gmsh.model.mesh.getNodes()
    points=np.asarray(flat).reshape(-1,3)
    order=np.argsort(node_tags); sorted_tags=np.asarray(node_tags)[order]
    cells=[]; rid=[]; element_tags=[]
    for i,o in enumerate(objects):
        for tag in o["volume_tags"]:
            kinds,etags,conn=gmsh.model.mesh.getElements(3,tag)
            for kind,et,ns in zip(kinds,etags,conn):
                if kind!=4: raise RuntimeError(f"non-Tet4 volume element {kind}")
                cells.append(order[np.searchsorted(sorted_tags,np.asarray(ns))].reshape(-1,4))
                element_tags.append(np.asarray(et))
                rid.extend([i]*(len(ns)//4))
    cells=np.concatenate(cells); rid=np.array(rid,np.int32)
    # Gmsh minSICN in the same order as `cells`, so audit indices are solver indices.
    min_sicn=gmsh.model.mesh.getElementQualities(np.concatenate(element_tags),"minSICN")
    used=np.unique(cells)
    inv=np.full(len(points),-1,int); inv[used]=np.arange(len(used))
    points=points[used]; cells=inv[cells]
    A=points[cells[:,1:]]-points[cells[:,0,None]]
    det=np.linalg.det(A)
    if np.any(det<=0): raise RuntimeError("nonpositive tetrahedral volume")
    volumes=det/6
    for i,o in enumerate(objects):
        o["tetrahedra"]=int(np.count_nonzero(rid==i))
        if not o["tetrahedra"]: raise RuntimeError(f"body {o['id']} lost all elements")
        o["mesh_volume_mm3"]=float(volumes[rid==i].sum())
        o["volume_error_pct"]=100*(o["mesh_volume_mm3"]/o["cad_volume_mm3"]-1)
    # Face multiplicities prove actual interface sharing, beyond coincident coordinates.
    faces=np.concatenate([cells[:,p] for p in [(0,2,1),(0,1,3),(1,2,3),(2,0,3)]])
    owners=np.tile(np.arange(len(cells)),4)
    keys=np.sort(faces,axis=1)
    sorter=np.lexsort(keys.T[::-1]); keys=keys[sorter]; faces=faces[sorter]; owners=owners[sorter]
    _,starts,counts=np.unique(keys,axis=0,return_index=True,return_counts=True)
    if counts.max()>2: raise RuntimeError("nonmanifold tet face")
    bnd=faces[starts[counts==1]]; bnd_owner=owners[starts[counts==1]]
    double=starts[counts==2]
    pairs=np.sort(np.column_stack([rid[owners[double]],rid[owners[double+1]]]),axis=1)
    pairs=pairs[pairs[:,0]!=pairs[:,1]]
    adjacency=[]
    for (i,j),n in zip(*np.unique(pairs,axis=0,return_counts=True)):
        adjacency.append(dict(a=objects[i]["id"],b=objects[j]["id"],shared_triangles=int(n)))
    # All physical volumes must belong to one face-connected material assembly.
    connected={0}
    while True:
        old=len(connected)
        for i,j in pairs:
            if i in connected or j in connected: connected.update([int(i),int(j)])
        if len(connected)==old: break
    if len(connected)!=len(objects): raise RuntimeError("disconnected material assembly")
    z=points[bnd][:,:,2]
    top=bnd[np.all(np.isclose(z,2.7,atol=1e-8),axis=1)]
    bottom=bnd[np.all(np.isclose(z,-1.,atol=1e-8),axis=1)]
    if not len(top) or not len(bottom): raise RuntimeError("missing cooling boundary")
    audit,gamma,condition=quality_audit(points,cells,rid,objects,min_sicn)
    audit["optimizer"]=optimizer
    audit["gmsh_options"]=dict(Algorithm3D=gmsh.option.getNumber("Mesh.Algorithm3D"),
                               Optimize=gmsh.option.getNumber("Mesh.Optimize"),
                               OptimizeNetgen=gmsh.option.getNumber("Mesh.OptimizeNetgen"),
                               MeshSizeMin=gmsh.option.getNumber("Mesh.MeshSizeMin"),
                               MeshSizeMax=gmsh.option.getNumber("Mesh.MeshSizeMax"),
                               MeshSizeFromCurvature=gmsh.option.getNumber("Mesh.MeshSizeFromCurvature"))
    (out/"quality.json").write_text(json.dumps(audit,indent=2))
    np.savez_compressed(out/"quality.npz",gamma=gamma,edge_condition=condition,
                        min_sicn=np.asarray(min_sicn),region_id=rid)
    np.savez_compressed(out/"mesh.npz",points_m=points*1e-3,tets=cells,
                        region_id=rid,boundary=bnd,boundary_owner=bnd_owner,
                        top=top,bottom=bottom,volume_m3=volumes*1e-9)
    metadata=dict(case="stacked_memory_package",fidelity="illustrative synthetic package; not a product stackup",
                  units_geometry="mm",units_solver="m",mesh_size_mm=h,
                  nodes=len(points),elements=len(cells),cad_bodies=len(objects),
                  materials=sorted(set(o["material"] for o in objects)),
                  min_volume_mm3=float(volumes.min()),quality=audit,objects=objects,adjacency=adjacency,
                  face_connected_components=1,nonmanifold_faces=0,total_power_W=sum(o["power_W"] for o in objects),
                  gmsh_version=gmsh.__version__,elapsed_s=time.time()-started,
                  script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out/"geometry.json").write_text(json.dumps(metadata,indent=2))
    gmsh.finalize()
    print(json.dumps({k:v for k,v in metadata.items() if k not in ['objects','adjacency','quality']},indent=2))
    print(json.dumps({k:v for k,v in audit.items() if k!='worst_elements'},indent=2))
    for w in audit["worst_elements"][:8]: print("worst",json.dumps(w))


if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--h",type=float,default=.8)
    ap.add_argument("--optimizer",choices=["netgen","hxt","none"],default="netgen")
    ap.add_argument("--threads",type=int,default=1)
    args=ap.parse_args()
    build(args.output,args.h,args.optimizer,args.threads)
