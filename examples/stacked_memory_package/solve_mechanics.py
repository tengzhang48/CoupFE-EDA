"""One-way temperature -> linear thermoelasticity on the same package mesh.

Uses the public EDA thermo-mechanical weak-form interface and public CoupFE
native Tet4 code generation. The explicitly declared small-strain isotropic
material below uses engineering linear CTE, avoiding the different thermal
pressure convention of the existing neo-Hookean example. No plasticity.
"""
from pathlib import Path
import argparse
import hashlib
import importlib
import json
import sys
import time
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import splu

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # repository root
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import coupfe.codegen as au
from coupfe.codegen.core.tensor import trace
from coupfe.codegen.generators.uel_gen import generate_element
from coupfe.runtime.compiled_element import build_element_kernel
from coupfe import ElementGroup,CompiledElement,assemble_residual,assemble_tangent,newton_solve
from eda_multiphysics.thermomech_kernel import ThermoElastic, ThermoElasticMaterial, _vstate
from eda_multiphysics.tet_element import TET4_CONFIG
from solve_thermal import LinearThermalOperator, KERNELS

HERE=Path(__file__).resolve().parent
# All representative assumed values; not fitted to a product.
# E [GPa], nu, linear CTE [/K]. Conductivity sensitivity holds these fixed.
MATERIALS=dict(organic=(20.,.30,16e-6),silicon=(130.,.28,2.6e-6),
               attach=(1.,.35,40e-6),mold=(18.,.30,12e-6),
               copper=(110.,.34,17e-6),solder=(40.,.35,22e-6),
               top_tim=(.05,.35,60e-6))


class LinearMaterial(ThermoElasticMaterial):
    def stress_PK1(self,F,T):
        eps=.5*(F+F.T)-np.eye(3)
        return 2*self.G*eps+self.K*trace(eps)*np.eye(3)-(3*self.K+2*self.G)*self.alpha*T*np.eye(3)


class LinearProblem(ThermoElastic):
    material=LinearMaterial


def kernel():
    wd=KERNELS/'mechanics';wd.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(wd))
    try:return importlib.import_module('linear_thermo_tet4')
    except ImportError:
        problem=LinearProblem(ndim=3)
        problem.verify(state=_vstate(3),verbose=False)
        path=wd/'linear_thermo_tet4.for'
        generate_element(problem,str(path),backend='native',element_config=TET4_CONFIG,formulation='standard')
        return build_element_kernel(str(path),'linear_thermo_tet4',workdir=str(wd),backend='native')


def make_group(mod,points,cells,material):
    E,nu,alpha=material;E*=1e9
    mu=E/(2*(1+nu));lam=E*nu/((1+nu)*(1-2*nu))
    ce=CompiledElement(mod,props=(mu,lam,alpha,1.,1.),dof_per_node=4,n_svars=0,mcrd=3,n_elem=len(cells))
    return ElementGroup(ce,points,cells,dof_per_node=4,comps=(0,1,2,3))


def elastic_system(groups,points,T):
    n=len(points);U=np.zeros((n,4));U[:,3]=T
    m=(4*np.arange(n)[:,None]+np.arange(3)).ravel()
    K=assemble_tangent(groups,U.ravel(),None,0.,1.,4*n)[m][:,m]
    R,_=assemble_residual(groups,U.ravel(),None,0.,1.,4*n)
    return K.tocsr(),-R[m]


def verify(mod):
    p=np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0],[0,0,1],[1,0,1],[1,1,1],[0,1,1]],float)
    c=np.array([[0,1,2,6],[0,2,3,6],[0,3,7,6],[0,7,4,6],[0,4,5,6],[0,5,1,6]])
    mat=(10.,.3,1.3e-5);g=make_group(mod,p,c,mat)
    K,F=elastic_system([g],p,np.full(8,10.))
    bc={0:0.,1:0.,2:0.,4:0.,5:0.,11:0.}
    u,_,_=newton_solve([LinearThermalOperator(K,F)],np.zeros(24),None,24,bc,rtol=1e-10,maxit=3)
    expected=mat[2]*10*p
    error=float(np.max(np.abs(u.reshape(-1,3)-expected))/np.max(expected))
    if error>1e-8: raise RuntimeError(f'free thermal expansion failed {error}')
    # Full-constraint stress law is exact sigma=-E*alpha*dT/(1-2nu) I.
    sigma=LinearMaterial(G=10e9/(2*1.3),K=10e9*.3/(1.3*.4),alpha=1.3e-5).stress_PK1(np.eye(3),10.)
    constrained_error=float(np.max(np.abs(sigma+10e9*1.3e-5*10/.4*np.eye(3))))
    if constrained_error>1e-6: raise RuntimeError('thermal CTE convention error')
    _,Fzero=elastic_system([g],p,np.zeros(8))
    if np.max(np.abs(Fzero))>1e-9:raise RuntimeError('zero temperature mechanical load')
    return dict(free_expansion_relative_error=error,constrained_stress_error_Pa=constrained_error,
                zero_deltaT_load_max_N=float(np.max(np.abs(Fzero))))


def weighted_quantile(v,w,q):
    order=np.argsort(v);v=v[order];w=w[order]
    return float(v[np.searchsorted(np.cumsum(w),q*np.sum(w))])


def solve(root:Path):
    started=time.time();mod=kernel();checks=verify(mod)
    mesh=np.load(root/'mesh.npz');meta=json.loads((root/'geometry.json').read_text())
    thermal=json.loads((root/'result.json').read_text())
    p=mesh['points_m'];cells=mesh['tets'];rid=mesh['region_id'];vol=mesh['volume_m3']
    n=len(p);n3=3*n;objects=meta['objects'];rmat=np.array([o['material'] for o in objects])
    mids=(4*np.arange(n)[:,None]+np.arange(3)).ravel()
    groups=[];K=csr_matrix((n3,n3));U4=np.zeros(4*n)
    for name,mat in MATERIALS.items():
        subset=cells[rmat[rid]==name]
        print('mechanics assemble',name,len(subset),flush=True)
        g=make_group(mod,p,subset,mat);groups.append(g)
        K+=assemble_tangent([g],U4,None,0.,1.,4*n)[mids][:,mids]
    # Minimal 3-2-1 anchors on board corners remove rigid motion, permit expansion.
    anchors=[int(np.argmin(np.linalg.norm(p-np.array(x)*1e-3,axis=1)))
             for x in [(-11,-11,-1),(11,-11,-1),(-11,11,-1)]]
    fixed=np.array([3*anchors[0],3*anchors[0]+1,3*anchors[0]+2,
                    3*anchors[1]+1,3*anchors[1]+2,3*anchors[2]+2])
    free=np.setdiff1d(np.arange(n3),fixed)
    print('factor mechanics',len(free),'free DOFs',flush=True)
    factor=splu(K[free][:,free].tocsc())
    substrate_id=next(i for i,o in enumerate(objects) if o['id']=='substrate')
    substrate_nodes=np.unique(cells[rid==substrate_id]);top_nodes=substrate_nodes[np.isclose(p[substrate_nodes,2],.0007,atol=1e-10)]
    plane=np.column_stack([np.ones(len(top_nodes)),p[top_nodes,:2]])
    edge=p[cells[:,1:]]-p[cells[:,0,None]]
    active=np.array([o['power_W']>0 for o in objects])[rid]
    results={}
    for label in ['baseline','improved']:
        T=np.load(root/f'{label}_fields.npz')['temperature_C']
        U4=U4.reshape(n,4);U4[:,:3]=0.;U4[:,3]=T-40.
        R,_=assemble_residual(groups,U4.ravel(),None,0.,1.,4*n);F=-R[mids]
        u=np.zeros(n3);u[free]=factor.solve(F[free])
        residual=K@u-F;rel=float(np.linalg.norm(residual[free])/np.linalg.norm(F[free]))
        if not np.all(np.isfinite(u)) or rel>1e-7:raise RuntimeError(f'mechanical residual {rel}')
        disp=u.reshape(n,3)
        gu=np.linalg.solve(edge,disp[cells[:,1:]]-disp[cells[:,0,None]])
        eps=.5*(gu+np.swapaxes(gu,1,2))
        sigma=np.zeros_like(eps)
        for name,(E,nu,alpha) in MATERIALS.items():
            sel=rmat[rid]==name;mu=E*1e9/(2*(1+nu));lam=E*1e9*nu/((1+nu)*(1-2*nu))
            elastic=eps[sel]-alpha*(T[cells[sel]].mean(axis=1)-40.)[:,None,None]*np.eye(3)
            sigma[sel]=2*mu*elastic+lam*np.trace(elastic,axis1=1,axis2=2)[:,None,None]*np.eye(3)
        dev=sigma-np.trace(sigma,axis1=1,axis2=2)[:,None,None]/3*np.eye(3)
        vm=np.sqrt(1.5*np.sum(dev*dev,axis=(1,2)))*1e-6
        principal=np.linalg.eigvalsh(sigma)[:,-1]*1e-6
        detrended=disp[top_nodes,2]-plane@np.linalg.lstsq(plane,disp[top_nodes,2],rcond=None)[0]
        warpage=float(np.ptp(detrended)*1e6)
        result=dict(free_residual_relative=rel,substrate_warpage_um=warpage,
                    warpage_definition='peak-to-valley z displacement after least-squares plane removal on substrate top nodes',
                    active_die_mean_vm_MPa=float(np.average(vm[active],weights=vol[active])),
                    active_die_p95_vm_MPa=weighted_quantile(vm[active],vol[active],.95),
                    active_die_max_principal_MPa=float(principal[active].max()),
                    max_displacement_um=float(np.linalg.norm(disp,axis=1).max()*1e6),
                    anchors_node_ids=anchors,anchor_reactions_N=residual[fixed].tolist(),
                    net_force_N=np.sum(residual.reshape(n,3),axis=0).tolist())
        np.savez_compressed(root/f'{label}_mechanics.npz',displacement_m=disp,stress_MPa=sigma*1e-6,
                            von_mises_MPa=vm,principal_max_MPa=principal,substrate_top_nodes=top_nodes,
                            substrate_detrended_w_um=detrended*1e6,residual_N=residual)
        results[label]=result;print(label,json.dumps(result),flush=True)
    record=dict(coupling='one-way sequential steady Fourier -> linear thermoelasticity, identical mesh and node IDs',
        stress_free_reference_C=40.,materials_E_GPa_nu_alpha_per_K=MATERIALS,results=results,verification=checks,
        mechanical_BC='minimal 3-2-1 board-corner anchors; no distributed clamp; all external faces otherwise traction-free',
        physics='small strain isotropic elasticity; epsilon_thermal=alpha*(T-40 C)*I',
        scope='illustrative elastic sensitivity; no plasticity, cure stress, contact separation, fatigue, or predictive life',
        core_revision=thermal['core_revision'],eda_revision=thermal['eda_revision'],
        thermal_result_sha256=hashlib.sha256((root/'result.json').read_bytes()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),elapsed_s=time.time()-started)
    (root/'mechanics_result.json').write_text(json.dumps(record,indent=2))
    print('mechanics complete',record['elapsed_s'],flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mesh_dir',type=Path);a=ap.parse_args();solve(a.mesh_dir)
