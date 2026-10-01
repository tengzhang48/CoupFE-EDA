"""Steady thermal design comparison with public CoupFE/EDA native Tet4.

The conduction matrices come from CoupFE-EDA's existing generated native
electrothermal kernel with electric potential identically zero. Only the
temperature block is retained. Consistent volume heat loads and a consistent
triangular Robin boundary are application-level additions. The resulting
stateless operator is solved with CoupFE's normal Newton interface.
"""
from pathlib import Path
import argparse
import hashlib
import importlib
import json
import platform
import subprocess
import sys
import time
import numpy as np
from scipy.sparse import coo_matrix, csr_matrix

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # repository root

from coupfe import ElementGroup, CompiledElement, Residual, Tangent, assemble_tangent, newton_solve

HERE=Path(__file__).resolve().parent
CONDUCTIVITY=dict(organic=.8,attach=1.5,silicon=120.,mold=.8,copper=390.,solder=50.)
AMBIENT_C=40.
H_TOP=4000.  # prescribed effective cold-plate coupling, W/(m^2 K); not CFD


class LinearThermalOperator:
    """Exact cache of a temperature-independent compiled bulk + boundary operator."""
    def __init__(self,K,F):
        self.K=K.tocsr(); self.F=F; self.coo=self.K.tocoo(); self.dofs=np.arange(len(F))
    def residual(self,U,state,t,dt):
        return Residual(self.dofs,self.K@U-self.F)
    def tangent(self,U,state,t,dt):
        return Tangent(self.coo.row,self.coo.col,self.coo.data)
    def commit(self,U,state,t,dt): return state


KERNELS=HERE/'_kernels'   # generated and compiled on first use; not tracked


def native_module():
    """CoupFE-EDA's generated native electrothermal Tet4 kernel (built once)."""
    wd=KERNELS/'thermal';wd.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(wd))
    try: return importlib.import_module('et_tet4_native_kernel')
    except ImportError:
        from eda_multiphysics.etv_kernel import build_et_kernel
        return build_et_kernel(wd,element='Tet4',backend='native')


def compiled_matrix(module,points,cells,conductivity):
    ce=CompiledElement(module,props=(1.,0.,conductivity),dof_per_node=2,
                       n_svars=0,mcrd=3,n_elem=len(cells))
    group=ElementGroup(ce,points,cells,dof_per_node=2,comps=(0,1))
    n=len(points)
    K=assemble_tangent([group],np.zeros(2*n),None,0.,0.,2*n)
    return K[1::2,1::2].tocsr()


def affine_patch(module):
    # Six tetrahedra of a cube; linear T=x+2y+3z and exact face heat flux.
    points=np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0],
                     [0,0,1],[1,0,1],[1,1,1],[0,1,1]],float)
    cells=np.array([[0,1,2,6],[0,2,3,6],[0,3,7,6],[0,7,4,6],[0,4,5,6],[0,5,1,6]])
    K=compiled_matrix(module,points,cells,2.)
    # T=x, with only x end faces fixed, gives 2 W over a unit area at k=2.
    U=np.zeros(8)
    U[points[:,0]==1]=1.
    flux=float((K@U)[points[:,0]==1].sum())
    error=abs(flux-2.)
    if error>1e-11: raise RuntimeError("compiled cube Fourier flux check failed")
    return dict(cube_exact_flux_W=2.,cube_FE_flux_W=flux,absolute_error_W=error)


def solve(mesh_dir:Path):
    started=time.time(); meta=json.loads((mesh_dir/'geometry.json').read_text())
    mesh=np.load(mesh_dir/'mesh.npz',allow_pickle=False)
    points=mesh['points_m']; cells=mesh['tets']; rid=mesh['region_id']; volumes=mesh['volume_m3']
    n=len(points); module=native_module(); objects=meta['objects']
    print(f"Solving {mesh_dir.name}: {n} nodes, {len(cells)} native Tet4",flush=True)
    patch=affine_patch(module)
    region_mat=np.array([o['material'] for o in objects])
    Kbulk=csr_matrix((n,n))
    for material,k in CONDUCTIVITY.items():
        subset=cells[region_mat[rid]==material]
        print(f"  assemble {material}: {len(subset)} elements k={k}",flush=True)
        Kbulk+=compiled_matrix(module,points,subset,k)
    Ktim=compiled_matrix(module,points,cells[region_mat[rid]=='top_tim'],1.)
    F=np.zeros(n)
    for i,o in enumerate(objects):
        if o['power_W']:
            selected=rid==i; share=volumes[selected]/volumes[selected].sum()*o['power_W']/4
            np.add.at(F,cells[selected].ravel(),np.repeat(share,4))
    if abs(F.sum()-16.)>1e-10: raise RuntimeError("incorrect total die power")
    top=mesh['top']; p=points[top]
    areas=np.linalg.norm(np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0]),axis=1)/2
    rows=np.repeat(top,3,axis=1).ravel(); cols=np.tile(top,(1,3)).ravel()
    v=H_TOP*areas[:,None,None]*(np.ones((3,3))+np.eye(3))[None,:,:]/12
    H=coo_matrix((v.ravel(),(rows,cols)),shape=(n,n)).tocsr()
    bottom=np.unique(mesh['bottom']); free=np.ones(n,bool); free[bottom]=False
    if not np.isclose(areas.sum(),18e-3**2,rtol=1e-9): raise RuntimeError("lid cooling coverage")
    results={}
    for label,k in [('baseline',1.),('improved',5.)]:
        K=Kbulk+k*Ktim+H
        op=LinearThermalOperator(K,F)
        theta,_,iterations=newton_solve([op],np.zeros(n),None,n,
                                        {int(i):0. for i in bottom},rtol=1e-9,maxit=4)
        R=K@theta-F
        relative_residual=float(np.linalg.norm(R[free])/np.linalg.norm(F[free]))
        top_W=float((H@theta).sum()); bottom_W=float(-R[bottom].sum())
        balance=abs(top_W+bottom_W-F.sum())/F.sum()
        if not np.all(np.isfinite(theta)) or relative_residual>1e-8 or balance>1e-8 or theta.min()<-1e-7:
            np.savez_compressed(mesh_dir/f'{label}_diagnostic.npz',temperature_rise_K=theta)
            raise RuntimeError(f"failed thermal solution {label}: residual={relative_residual} balance={balance} min_rise={theta.min()} max_rise={theta.max()}")
        T=AMBIENT_C+theta
        centroids=T[cells].mean(axis=1)
        # Exact linear Tet4 element gradient, used for heat-flux visualization.
        edge=points[cells[:,1:]]-points[cells[:,0,None]]
        grad=np.linalg.solve(edge,(T[cells[:,1:]]-T[cells[:,0,None]])[...,None])[...,0]
        conductivity=np.array([k if o['material']=='top_tim' else CONDUCTIVITY[o['material']] for o in objects])
        flux=-conductivity[rid,None]*grad
        measurements=[]
        for i,o in enumerate(objects):
            selected=rid==i
            measurements.append(dict(id=o['id'],material=o['material'],power_W=o['power_W'],
                     mean_C=float(np.average(centroids[selected],weights=volumes[selected])),
                     peak_C=float(T[np.unique(cells[selected])].max())))
        die_metrics=[r for r in measurements if r['power_W']>0]
        result=dict(top_tim_k_W_mK=k,peak_die_C=max(r['peak_C'] for r in die_metrics),
                    peak_all_C=float(T.max()),peak_location_m=points[int(T.argmax())].tolist(),
                    min_C=float(T.min()),power_W=float(F.sum()),top_removed_W=top_W,
                    board_removed_W=bottom_W,balance_error_relative=float(balance),
                    free_residual_relative=relative_residual,newton_iterations=iterations,
                    dies=die_metrics,objects=measurements)
        results[label]=result
        np.savez_compressed(mesh_dir/f'{label}_fields.npz',temperature_C=T,heat_flux_W_m2=flux,
                            source_nodal_W=F,residual_W=R)
        print(label,json.dumps({k:v for k,v in result.items() if k not in ['dies','objects']}),flush=True)
    # A zero-power control of the same linear problem must have zero temperature rise.
    zero,_,_=newton_solve([LinearThermalOperator(K,np.zeros(n))],np.zeros(n),None,n,
                          {int(i):0. for i in bottom},rtol=1e-9,maxit=2)
    zero_error=float(np.max(np.abs(zero)))
    if zero_error>1e-12: raise RuntimeError("zero power control")
    def git_ref(path):
        try: return subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True,
                                            stderr=subprocess.DEVNULL).strip()
        except (OSError,subprocess.CalledProcessError): return 'unknown (not a git checkout)'
    import coupfe,eda_multiphysics
    record=dict(geometry=meta,conductivity_W_mK={**CONDUCTIVITY,'top_tim':[1.,5.]},
                reference_C=AMBIENT_C,top_h_W_m2K=H_TOP,
                bottom_boundary='board bottom fixed at 40 C',other_boundary='adiabatic',
                contact='conformal shared nodes; explicit finite TIM/attach volumes; perfect contact between touching solids',
                equations='steady isotropic Fourier conduction; prescribed uniform per-die volumetric power',
                assumptions=['synthetic stackup and representative assumed properties','no resolved TSVs or microbumps',
                             'no thermal contact resistance beyond explicit layers','no temperature-dependent properties',
                             'no mechanical deformation, transient, CFD, or device validation'],
                results=results,verification={**patch,'zero_power_max_rise_K':zero_error},
                peak_reduction_C=results['baseline']['peak_die_C']-results['improved']['peak_die_C'],
                core_revision=git_ref(Path(coupfe.__file__).parents[1]),
                eda_revision=git_ref(Path(eda_multiphysics.__file__).parents[1]),
                python=sys.version,platform=platform.platform(),elapsed_s=time.time()-started,
                driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                mesh_sha256=hashlib.sha256((mesh_dir/'mesh.npz').read_bytes()).hexdigest())
    (mesh_dir/'result.json').write_text(json.dumps(record,indent=2))
    print(f"Peak reduction {record['peak_reduction_C']:.6f} C; elapsed {record['elapsed_s']:.1f}s",flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('mesh_dir',type=Path); args=ap.parse_args(); solve(args.mesh_dir)
