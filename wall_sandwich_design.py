"""Simplified sectional design, EC2-2 LL.108-115 + EC2-1-1 F.1, 6.2.
Tension positive; physical moment convention M=int(z*N) (kNm/m).
Uniform exterior concrete stress, tension-only orthogonal reinforcement;
no non-linear constitutive assumptions. Iterate eccentric steel forces with
actual net concrete centroids, certifying N/M equilibrium. No installed links
are assumed, no claim about global stability, local anchorage or CQC signs.
LL is supplementary to the building code; conservative concrete bounds below.
"""
import numpy as np
import pandas as pd
from wall_physical_layers import layout, LABELS
from wall_resultant_shear import resultant_shear, transfer_shear_reserve
from wall_coupled_shear import truss_increment


def face_opt(n):
    """F.2-7 optimum; compression-positive formulas transformed to tension +."""
    x,y,q=n.T; a=np.abs(q); swap=x>y; u=np.minimum(x,y);v=np.maximum(x,y)
    both=(x+y)/2+np.hypot((x-y)/2,q)<=0
    b=-u>a
    bb=np.divide(a*a,-u,out=np.zeros_like(a),where=b)
    tx=np.where(b,0.,u+a);ty=np.where(b,v+bb,v+a)
    s=np.maximum(np.stack([np.where(swap,ty,tx),np.where(swap,tx,ty)],axis=1),0.)
    s[both]=0.
    return s


def layers(h,fam,t):
    """Uniform compression resultant at net area centroid of each band."""
    out=[]
    for side,t in zip((1,-1),np.broadcast_to(t,(2,))):
        fs=[f for f in fam if f.bar.z_mm*side>0]
        if not fs or any(h/2-abs(f.bar.z_mm)+f.phi/2>t+1e-8 for f in fs):raise ValueError('Varão fora da camada')
        a=np.array([f.bar.area_mm2_m/1000 for f in fs]); zs=np.array([f.bar.z_mm for f in fs]); axes=np.array([f.bar.axis for f in fs])
        net=t-a.sum()
        if net<=0:raise ValueError('Área líquida não positiva')
        zc=(side*t*(h/2-t/2)-a@zs)/net
        area=np.array([a[axes==j].sum() for j in (0,1)])
        if min(area)<=0:raise ValueError('Falta armadura')
        zsteel=np.array([np.average(zs[axes==j],weights=a[axes==j]) for j in (0,1)])
        out.append((net,zc,area,zsteel))
    return out


def compression_limit(force, steel, net, fck, fcd, fyd, area, elastic):
    """F.1 + supplementary 6.109(103), using gross elastic shell stress.

    No angle clipping. Actual steel stress is based on provided area. The
    6.111 / 6.112 branches require their respective hypotheses; other mixed
    fields retain a conservative screening bound, not a 6.109 certificate.
    The F.1 bound is retained even where 6.109 permits a higher stress.
    """
    c=force.copy();c[:,:2]-=steel
    mean=(c[:,0]+c[:,1])/2;rad=np.hypot((c[:,0]-c[:,1])/2,c[:,2]);lo=mean-rad;hi=mean+rad
    fmean=(force[:,0]+force[:,1])/2;frad=np.hypot((force[:,0]-force[:,1])/2,force[:,2]);pure=fmean+frad<=0
    nu=.6*(1-fck/250)
    alpha=np.clip(np.divide(hi,lo,out=np.zeros_like(lo),where=lo<0),0,1)
    biax=.85*fcd*(1+3.8*alpha)/(1+alpha)**2
    dev=np.stack((c[:,0]-c[:,1],2*c[:,2]),axis=1)
    eldev=np.stack((elastic[:,0]-elastic[:,1],2*elastic[:,2]),axis=1)
    enorm=np.linalg.norm(eldev,axis=1);cnorm=np.linalg.norm(dev,axis=1)
    emin=(elastic[:,0]+elastic[:,1]-enorm)/2
    angle_ok=(enorm>1e-10)&(cnorm>1e-9)&(emin<0)
    cosine=np.divide(np.sum(dev*eldev,axis=1),cnorm*enorm,out=np.zeros_like(lo),where=angle_ok)
    angle=np.where(angle_ok,.5*np.degrees(np.arccos(np.clip(cosine,-1,1))),np.nan)
    steel_ratio=np.max(steel/(area*fyd),axis=1)
    aligned=angle_ok&(angle<=1e-5)&(steel_ratio<1-1e-8)
    yielding=angle_ok&(angle<=15+1e-8)&(steel_ratio>=1-1e-8)&(steel_ratio<=1+1e-8)
    no_c=-lo<=1e-9
    limit=np.full(len(lo),.52*nu*fcd)
    rule=np.full(len(lo),'Limite conservador; 6.109 não demonstrado',dtype=object)
    limit[aligned]=np.minimum(nu*fcd,fcd*(.85-steel_ratio[aligned]*(.85-nu)))
    rule[aligned]='6.111 + F.1'
    limit[yielding]=nu*fcd*(1-.032*angle[yielding]);rule[yielding]='6.112 + F.1'
    limit[pure]=np.minimum(fcd,biax[pure]);rule[pure]='6.110 + F.1'
    limit[no_c]=fcd;rule[no_c]='Sem compressão'
    valid=hi<=1e-7*np.maximum(1,np.abs(c).sum(axis=1))
    return c,np.maximum(0,-lo)/(net*limit),valid,angle,limit,rule,steel_ratio


def elastic_face(h,n,m,z):
    """Homogeneous gross-section elastic plane stress at the band centroid."""
    return n/h+12000*m*z/h**3


def aligned_steel(force, elastic):
    """F.8-10 with elastic direction, subject to F.1 redistribution bounds.
    Falls back to optimum if an aligned field does not satisfy those bounds.
    """
    opt=face_opt(force);x,y,q=force.T;ex,ey,et=elastic.T
    dev=np.hypot(ex-ey,2*et);elo=(ex+ey-dev)/2
    a=np.abs(q);good=(a>1e-10)&(np.abs(et)>1e-12)&(q*et>0)&(elo<0)
    # Compressive principal direction: cot(theta)=|v_x/v_y|.
    cot=np.divide(ey-elo,np.abs(et),out=np.ones_like(a),where=good)
    good &= (cot>1e-9)&(cot<1e9)
    cand=np.stack((x+a*cot,y+np.divide(a,cot,out=np.zeros_like(a),where=cot>0)),axis=1)
    tol=1e-8*np.maximum(1,opt.max(axis=1))
    good &= np.all((cand>=.5*opt-tol[:,None])&(cand<=2*opt+tol[:,None])&(cand>=-tol[:,None]),axis=1)
    return np.where(good[:,None],np.maximum(0,cand),opt)


def yielded_steel(force, area, fyd, axis):
    """F.8-10 field with one actual family at fyd, no invented steel area.

    Return optimum on invalid candidates, with a separate validity mask.
    A zero shear does not determine a finite strut angle via F.8-10.
    """
    force=np.asarray(force,float); opt=face_opt(force); cap=np.asarray(area)*fyd
    x,y,q=force.T; a=np.abs(q)
    denom=cap[axis]-force[:,axis]
    good=(a>1e-10)&(denom>1e-10)
    other=1-axis
    cand=np.empty_like(opt);cand[:,axis]=cap[axis]
    cand[:,other]=force[:,other]+np.divide(a*a,denom,out=np.zeros_like(a),where=good)
    tol=1e-8*np.maximum(1,opt.max(axis=1))
    good &= np.all((cand>=.5*opt-tol[:,None])&(cand<=2*opt+tol[:,None])&(cand>=-tol[:,None])&(cand<=cap+1e-8),axis=1)
    return np.where(good[:,None],np.maximum(0,cand),opt),good


def demonstrated_steel(force, elastic, area, net, fck, fcd, fyd):
    """Choose from F optimum/aligned and exact-yield fields for a face.

    Prefer certified passing fields; final equilibrium and actual steel
    stress are recomputed after the coupled eccentricity iteration.
    """
    best=aligned_steel(force,elastic)
    _,u,ok,_,_,rule,sr=compression_limit(force,best,net,fck,fcd,fyd,area,elastic)
    rank=np.where(ok&(u<=1+1e-7)&(sr<=1+1e-8)&~np.char.startswith(rule.astype(str),'Limite'),0,1)
    score=u.copy()
    for axis in (0,1):
        cand,valid=yielded_steel(force,area,fyd,axis)
        _,uc,okc,_,_,rc,src=compression_limit(force,cand,net,fck,fcd,fyd,area,elastic)
        valid &= okc&(uc<=1+1e-7)&(src<=1+1e-8)&(rc=='6.112 + F.1')
        take=valid&((rank>0)|(uc<score-1e-9))
        best[take]=cand[take];score[take]=uc[take];rank[take]=0
    return best


def exact_aligned_faces(n,mforce,layers_,elastic,fck,fcd,fyd):
    """Analytic LL.115 equilibrium for F.8-10 elastic-aligned fields.

    On each face the tensile forces are either zero (biaxial compression)
    or N_x + |N_xy| cot(theta_el), N_y + |N_xy|/cot(theta_el).
    Solve the affine equilibrium for each of the four branch combinations,
    then check F redistribution at the final split, not during iteration.
    No angle relaxation, no assumed yield, no clipping tensile demands.
    Returns a candidate only if the complete two-face field is admissible.
    """
    ap,zp,asp,zsp=layers_[0];am,zm,asm,zsm=layers_[1];z=zp-zm
    base=(mforce-zm*n)/z
    ep,em=elastic
    def constants(q,el):
        x,y,t=el.T; dev=np.hypot(x-y,2*t); emin=(x+y-dev)/2
        good=(np.abs(q)>1e-10)&(np.abs(t)>1e-12)&(q*t>0)&(emin<0)
        cot=np.divide(y-emin,np.abs(t),out=np.ones_like(q),where=good)
        good &= (cot>1e-9)&(cot<1e9)
        cot=np.where(good,cot,1.)
        return np.column_stack((np.abs(q)*cot,np.abs(q)/cot)),good
    cp,gp=constants(base[:,2],ep);cm,gm=constants(n[:,2]-base[:,2],em)
    xp,xm=zsp-zp,zsm-zm
    best=np.full(len(n),np.inf);candidate=base.copy();splus=np.zeros((len(n),2));sminus=splus.copy()
    for i,j in ((0,0),(0,1),(1,0),(1,1)):
        den=z+i*xp-j*xm
        if np.any(np.abs(den)<1e-9):continue
        p=base.copy();p[:,:2]=(z*base[:,:2]-i*xp*cp-j*xm*(n[:,:2]+cm))/den
        b=n-p; sp=i*(p[:,:2]+cp);sm=j*(b[:,:2]+cm)
        valid=np.ones(len(n),bool)
        for f,steel,active,direction,area,net,el in ((p,sp,i,gp,asp,ap,ep),(b,sm,j,gm,asm,am,em)):
            opt=face_opt(f);tol=1e-8*np.maximum(1,opt.max(axis=1))
            principal=(f[:,0]+f[:,1])/2+np.hypot((f[:,0]-f[:,1])/2,f[:,2])
            if active:valid &= direction&(principal>0)&np.all((steel>=0)&(steel>=.5*opt-tol[:,None])&(steel<=2*opt+tol[:,None]),axis=1)
            else:valid &= principal<=1e-10
            _,u,ok,_,_,rule,sr=compression_limit(f,steel,net,fck,fcd,fyd,area,el)
            valid &= ok&(sr<=1+1e-8)&~np.char.startswith(rule.astype(str),'Limite')
            if f is p:score=np.maximum(u,sr)
            else:score=np.maximum(score,np.maximum(u,sr))
        take=valid&(score<best)
        best[take]=score[take];candidate[take]=p[take];splus[take]=sp[take];sminus[take]=sm[take]
    return candidate,splus,sminus,best


def solve_faces(n,m,layers_,fck,fcd,fyd,*,elastic=None,align=False,yield_search=False,detail=False):
    """Solve LL face split with exact correction for eccentric tensile steel.
    Fixed-point search is bounded. Only certified residuals are accepted;
    a failed search is not proof of structural insufficiency.
    """
    ap,zp,asp,zsp=layers_[0];am,zm,asm,zsm=layers_[1];z=zp-zm
    mforce=m*1000
    if elastic is None:
        # Direct API tests: nominal elastic face stress is an illustrative reference.
        elastic=((mforce-zm*n)/z/ap,(zp*n-mforce)/z/am)
    ep,em=elastic
    def demand(p,b):
        if yield_search:
            return (demonstrated_steel(p,ep,asp,ap,fck,fcd,fyd),demonstrated_steel(b,em,asm,am,fck,fcd,fyd))
        return (aligned_steel(p,ep),aligned_steel(b,em)) if align else (face_opt(p),face_opt(b))
    p=(mforce-zm*n)/z; base=p.copy()
    for _ in range(60):
        b=n-p; sp,sm=demand(p,b)
        ecc=(zsp-zp)*sp+(zsm-zm)*sm
        corrected=base.copy();corrected[:,:2]-=ecc/z
        diff=np.max(np.abs(corrected-p),axis=1)
        p=.5*p+.5*corrected
        if np.max(diff,initial=0)<1e-8:break
    b=n-p;sp,sm=demand(p,b)
    cp,up,okp,angp,limp,rp,srp=compression_limit(p,sp,ap,fck,fcd,fyd,asp,ep);cm,um,okm,angm,limm,rm,srm=compression_limit(b,sm,am,fck,fcd,fyd,asm,em)
    if align and not yield_search:
        pc,sc,tc,score=exact_aligned_faces(n,mforce,layers_,(ep,em),fck,fcd,fyd)
        prev=np.maximum.reduce([up,um,srp,srm])
        pending=np.char.startswith(rp.astype(str),'Limite')|np.char.startswith(rm.astype(str),'Limite')
        take=np.isfinite(score)&(score<=1+1e-7)&(pending|~okp|~okm|(score<prev-1e-9))
        if take.any():
            p[take]=pc[take];b=n-p;sp[take]=sc[take];sm[take]=tc[take]
            cp,up,okp,angp,limp,rp,srp=compression_limit(p,sp,ap,fck,fcd,fyd,asp,ep);cm,um,okm,angm,limm,rm,srm=compression_limit(b,sm,am,fck,fcd,fyd,asm,em)

    recon=zp*p+zm*b;recon[:,:2]+=(zsp-zp)*sp+(zsm-zm)*sm
    res=np.max(np.abs(recon-mforce),axis=1)/1000
    ok=okp&okm&(res<=1e-7*np.maximum(1,np.abs(m).max(axis=1)))
    steel=np.stack((sp[:,0],sm[:,0],sp[:,1],sm[:,1]),axis=1)
    cap=np.array([asp[0],asm[0],asp[1],asm[1]])*fyd
    result=(steel*1000/fyd,np.max(steel/cap,axis=1),np.maximum(up,um),res,ok,p,b)
    return result+(angp,angm,limp,limm,rp,rm,up,um) if detail else result


def assess(h,fam,n,m,q,fck,fcd,gamma_c,fyk,fyd):
    """Bounded symmetric/asymmetric band search, LL shear result and F optimum.
    A no-tie solution uses 6.2.2; otherwise cot=1 and full VEd (no VRdc
    addition), plus LL longitudinal forces; additionally restrict stress in
    the reserved core, including tie demand based on the smaller effective depth. Tie design conditional on actual detailing.
    """
    n,m,q=map(lambda v:np.asarray(v,float),(n,m,q))
    if n.ndim!=2 or n.shape[1]!=3 or m.shape!=n.shape or q.shape!=(len(n),2) or not np.isfinite(np.c_[n,m,q]).all():raise ValueError('Tensor incompleto')
    if not len(n):raise ValueError('Sem linhas ELU')
    v=np.linalg.norm(q,axis=1)
    sh=resultant_shear(h,fam,n,q,fck,fcd,gamma_c,compression_credit=True)
    vrdc=sh['PhysShear_VRdc_kN_m'];need=v>vrdc+1e-8
    delta=truss_increment(q)*need[:,None]
    nfaces=n+delta
    tmin=np.array([max(h/2-abs(f.bar.z_mm)+f.phi/2 for f in fam if f.bar.z_mm*side>0) for side in (1,-1)])
    # 30 mm reserved core is a search assumption, not a detailing rule.
    tmax=(h-30)/2
    if tmin.sum()>h-30+1e-8:raise ValueError('Núcleo reservado insuficiente')
    fields=['util','steel_util','concrete_util','shear_util','core_mm','band_plus_mm','band_minus_mm','core_z_mm','z_mm','VRdc_kN_m','VRdmax_kN_m','Asw_req_mm2_m2','residual_kNm_m','Nplus_x','Nplus_y','Nplus_xy','Nminus_x','Nminus_y','Nminus_xy','angle_plus_deg','angle_minus_deg','fcd_lim_plus_MPa','fcd_lim_minus_MPa','concrete_util_plus','concrete_util_minus','transfer_Nx_kN_m','transfer_Ny_kN_m']
    out={k:np.full(len(n),np.nan) for k in fields};out.update({k:np.full(len(n),'Sem resultado',dtype=object) for k in ('compression_rule_plus','compression_rule_minus')});best=np.full(len(n),np.inf);reqbest=np.full((len(n),4),np.nan);rank=np.full(len(n),3,dtype=int)
    def trial(tp,tm,idx):
        core=h-tp-tm
        if not len(idx) or core<30-1e-8:return
        ls=layers(h,fam,(tp,tm));z=min(ls[0][1]-ls[1][1],.9*min(h/2+abs(f.bar.z_mm) for f in fam))
        core_z=(tm-tp)/2
        cap=min(z,core)*.6*(1-fck/250)*fcd/2
        vi=v[idx];ci=vrdc[idx];ni=need[idx]
        vs=np.where(ni,vi/cap,np.divide(vi,ci,out=np.where(vi==0,0.,np.inf),where=ci>0))
        asw=np.where(ni,np.maximum(vi*1e6/(min(z,core)*fyd),.08*np.sqrt(fck)/fyk*1e6),0.)
        # Core compression -delta has moment -delta*core_z/1000.
        ep=elastic_face(h,n[idx],m[idx],ls[0][1]);em=elastic_face(h,n[idx],m[idx],ls[1][1])
        def evaluate(j,align,yield_search=False):
            if not len(j):return
            ii=idx[j]
            req,us,uc,res,ok,p,b,ap,am,lp,lm,rp,rm,up,um=solve_faces(nfaces[ii],m[ii]+delta[ii]*core_z/1000,ls,fck,fcd,fyd,elastic=(ep[j],em[j]),align=align,yield_search=yield_search,detail=True)
            util=np.maximum.reduce([us,uc,vs[j]])
            conditional=np.char.startswith(rp.astype(str),'Limite')|np.char.startswith(rm.astype(str),'Limite')
            # Prefer demonstrated compression conditions over a passing screen,
            # but never choose a failing candidate instead of a passing one.
            newrank=np.where(util<=1+1e-7,conditional.astype(int),2)
            take=ok&np.isfinite(util)&((newrank<rank[ii])|((newrank==rank[ii])&(util<best[ii])));sel=ii[take]
            rank[sel]=newrank[take]
            best[sel]=util[take];reqbest[sel]=req[take]
            full=lambda x:np.full(len(j),x)
            nominal=((m[ii]+delta[ii]*core_z/1000)*1000-ls[1][1]*nfaces[ii])/(ls[0][1]-ls[1][1])
            transfer=p[:,:2]-nominal[:,:2]
            vals=[util,us,uc,vs[j],full(core),full(tp),full(tm),full(core_z),full(z),ci[j],full(cap),asw[j],res,*p.T,*b.T,ap,am,lp,lm,up,um,*transfer.T]
            for k,val in zip(fields,vals):out[k][sel]=val[take]
            out['compression_rule_plus'][sel]=rp[take];out['compression_rule_minus'][sel]=rm[take]
        evaluate(np.arange(len(idx)),False)
        # Alternate F.8-10 field where a demonstrated passing solution has not yet been found.
        evaluate(np.flatnonzero(rank[idx]>0),True)
        # Exact-yield alternatives are limited to cases with a viable candidate
        # at the nominal split; the coupled solution is certified separately.
        remain=np.flatnonzero(rank[idx]>0)
        if len(remain):
            ii=idx[remain]; nominal=((m[ii]+delta[ii]*core_z/1000)*1000-ls[1][1]*nfaces[ii])/(ls[0][1]-ls[1][1])
            possible=np.zeros(len(remain),dtype=bool)
            for face,L,el in ((nominal,ls[0],ep[remain]),(nfaces[ii]-nominal,ls[1],em[remain])):
                for axis in (0,1):
                    candidate,valid=yielded_steel(face,L[2],fyd,axis)
                    _,uc,okc,_,_,rc,_=compression_limit(face,candidate,L[0],fck,fcd,fyd,L[2],el)
                    possible |= valid&okc&(uc<=1+1e-7)&(rc=='6.112 + F.1')
            evaluate(remain[possible],True,True)
    if tmin.max()<=tmax+1e-8:
        ts=np.unique(np.clip(np.r_[tmin.max(),h*np.array([.30,.35,.40,.45]),tmax],tmin.max(),tmax))
        for t in ts:trial(t,t,np.arange(len(n)))
    # LL.115: vary face thicknesses only for unresolved lines; keep core.
    idx=np.flatnonzero(best>1+1e-7)
    if len(idx):
        tps=np.unique(np.r_[tmin[0],np.clip(h*np.arange(.25,.66,.05),tmin[0],h-30-tmin[1]),h-30-tmin[1]])
        tms=np.unique(np.r_[tmin[1],np.clip(h*np.arange(.25,.66,.05),tmin[1],h-30-tmin[0]),h-30-tmin[0]])
        for tp in tps:
            for tm in tms:
                if abs(tp-tm)>1e-8:trial(tp,tm,idx)
    out['status']=np.where(~np.isfinite(best),'Sem equilíbrio demonstrado',np.where(best>1+1e-7,'Modelo sandwich não satisfeito',np.where(need,'Armadura de corte proposta; por confirmar','Satisfeito no modelo de 1.ª ordem; amarração por confirmar')))
    pending=np.char.startswith(out['compression_rule_plus'].astype(str),'Limite conservador')|np.char.startswith(out['compression_rule_minus'].astype(str),'Limite conservador')
    out['status']=np.where(pending & np.isfinite(best),np.where(best>1+1e-7,'Modelo sandwich não satisfeito no limite de triagem; 6.109 não demonstrado',np.where(need,'Armadura de corte proposta; limite de triagem satisfeito; 6.109 não demonstrado','Limite de triagem satisfeito; 6.109 não demonstrado; amarração por confirmar')),out['status'])
    out['transfer_VRdc_lower_kN_m'],out['transfer_reserve_kN_m']=transfer_shear_reserve(h,fam,n,q,fck,fcd,gamma_c)
    out['transfer_force_norm_kN_m']=np.hypot(out['transfer_Nx_kN_m'],out['transfer_Ny_kN_m'])
    out['transfer_status']=np.where(~np.isfinite(best),'Sem resultado',np.where(np.hypot(out['transfer_Nx_kN_m'],out['transfer_Ny_kN_m'])>1e-7,'LL.115: corte adicional por verificar (gradiente espacial)','Sem correção excêntrica local; continuidade por confirmar'))
    for j,k in enumerate(LABELS):out['As_req_'+k]=reqbest[:,j]
    return out


def intact_ll_bound(h,n,m,q,fck,fcd,gamma_c):
    """Sufficient bound for LL(103),(107), not a history certificate.

    Gross rectangular section, tension-positive, zero transverse normal
    stress and parabolic Q. At any depth sqrt(J2)=||dev(S)||_F/sqrt(2).
    The affine plane-stress contribution is convex in depth, hence bounded
    by the two faces; the shear contribution is bounded by 1.5|Q|/h.
    lambda <= c1 in LL.107, I1 is affine. The resulting upper bound on
    LL.101 is valid throughout the thickness, not just at sampled points.
    Also require a conservative tensile design-strength bound and fcd.
    """
    n,m,q=map(lambda a:np.asarray(a,float),(n,m,q))
    if h<=0 or min(fck,fcd,gamma_c)<=0 or not np.isfinite(np.c_[n,m,q]).all():
        raise ValueError('Dados inválidos para LL(107)')
    fcm=fck+8.;fctm=.3*fck**(2/3) if fck<=50 else 2.12*np.log1p(fcm/10.)
    k=fctm/fcm; alpha=1/(9*k**1.4); beta=1/(3.7*k**1.1); c1=1/(.7*k**.9)
    faces=np.stack((n/h+6000*m/h**2,n/h-6000*m/h**2),axis=1)
    x,y,t=faces.transpose(2,0,1)
    j2=(x*x+y*y-x*y)/3+t*t
    shear=1.5*np.linalg.norm(q,axis=1)/h
    root=np.sqrt(np.maximum(0,j2)).max(axis=1)+shear
    trace=(x+y).max(axis=1)
    phi=alpha*(root/fcm)**2+c1*root/fcm+beta*trace/fcm-1
    avg=(x+y)/2;rad=np.hypot((x-y)/2,t)
    tension=np.maximum(0,(avg+rad).max(axis=1))+shear
    comp=np.maximum(0,-(avg-rad).min(axis=1))+shear
    fctd=.7*fctm/gamma_c # alpha_ct=1, adopted EC2 reference
    ok=(phi<=0)&(tension<=fctd)&(comp<=fcd)
    return dict(intact_phi_upper=phi,intact_sigma_t_upper_MPa=tension,
                intact_sigma_c_upper_MPa=comp,intact_fctd_MPa=np.full(len(n),fctd),
                intact_util=comp/fcd,intact_candidate=ok)


def _run(d,mesh,n,m,q):
    fam=layout(d.t,d.cover,[d._parse_rebar_text(v.text if hasattr(v,'text') else v) for v in mesh],outer_axis=int(d.local_y_is_vertical))
    return assess(d.t,fam,n,m,q,d.fck,d.cp['fcd'],d.gamma_c,d.fyk,d.fyd)


def strip_allowances(d, mesh, g):
    """Use the same nominal-stiffness strip envelope as the final local check.

    Return additional moment magnitudes beyond the original WA envelope.
    Unavailable values remain NaN, never zero-certify a missing input.
    """
    result=np.zeros((len(g),2))
    for j,axis in enumerate('XY'):
        pair=2*j
        vals=g[['N'+axis*2,'M'+axis.lower()+'_pos','M'+axis.lower()+'_neg']].to_numpy(float)
        unique,inverse=np.unique(vals,axis=0,return_inverse=True)
        extra=[]
        for normal,mp,mm in unique:
            try:
                _,st=d.composite_detail(normal,mp,mm,mesh[pair],mesh[pair+1],axis,cross=(mesh[2-pair],mesh[3-pair]))
                if st['status'].startswith('Não requerida'): v=0.
                elif st['status'].startswith(('Dispensada','Incluída')):v=max(0.,st['moment']-max(mp,mm))
                else:v=np.nan
            except (ValueError,ArithmeticError):v=np.nan
            extra.append(v)
        result[:,j]=np.asarray(extra)[inverse]
    return result


def assess_envelope(d,mesh,n,m,q,extra):
    """Recheck signed original tensor plus nine discrete strip-allowance states.

    This covers both signs of the independent strip moments, not a general
    shell buckling analysis. In particular oblique compression is separate.
    Preserve the governing actual input and the coverage of every scenario.
    """
    n,m,q,extra=map(lambda x:np.asarray(x,float),(n,m,q,extra))
    base=_run(d,mesh,n,m,q)
    out={k:v.copy() for k,v in base.items()}
    out['util_first_order']=base['util'].copy()
    intact=intact_ll_bound(d.t,n,m,q,d.fck,d.cp['fcd'],d.gamma_c)
    out.update(intact)
    out['MEd_x_kNm_m']=m[:,0].copy();out['MEd_y_kNm_m']=m[:,1].copy()
    out['delta_Mx_kNm_m']=extra[:,0].copy();out['delta_My_kNm_m']=extra[:,1].copy()
    missing=~np.isfinite(extra).all(axis=1)
    # If one direction is pending, still evaluate the known directional allowance.
    ex=np.where(np.isfinite(extra),extra,0.)
    failure=~np.isfinite(base['util']);pending=np.char.find(base['status'].astype(str),'6.109 não demonstrado')>=0
    transfer=np.char.startswith(base['transfer_status'].astype(str),'LL.115')
    count=np.ones(len(n),int)
    for a,b in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
        # Skip duplicate states if the respective allowance is zero.
        idx=np.flatnonzero(((ex[:,0]>1e-10) if a else np.ones(len(n),bool)) & ((ex[:,1]>1e-10) if b else np.ones(len(n),bool)))
        if not len(idx):continue
        moments=m[idx].copy();moments[:,0]+=a*ex[idx,0];moments[:,1]+=b*ex[idx,1]
        trial=_run(d,mesh,n[idx],moments,q[idx]);count[idx]+=1
        check=intact_ll_bound(d.t,n[idx],moments,q[idx],d.fck,d.cp['fcd'],d.gamma_c)
        for k,v in check.items():
            if k=='intact_candidate':out[k][idx]&=v
            else:out[k][idx]=np.maximum(out[k][idx],v)
        failure[idx]|=~np.isfinite(trial['util'])
        pending[idx]|=np.char.find(trial['status'].astype(str),'6.109 não demonstrado')>=0
        transfer[idx]|=np.char.startswith(trial['transfer_status'].astype(str),'LL.115')
        take=np.isfinite(trial['util']) & (~np.isfinite(out['util'][idx]) | (trial['util']>out['util'][idx]))
        sel=idx[take]
        for k in base:
            if k.startswith('As_req_') or k in ('Asw_req_mm2_m2','transfer_force_norm_kN_m'):
                out[k][idx]=np.fmax(out[k][idx],trial[k])
            else:out[k][sel]=trial[k][take]
        out['MEd_x_kNm_m'][sel]=moments[take,0];out['MEd_y_kNm_m'][sel]=moments[take,1]
    out['status']=np.asarray(out['status'],dtype=object)
    out['transfer_status']=np.asarray(out['transfer_status'],dtype=object)
    out['status'][failure]='Sem equilíbrio demonstrado numa situação da envolvente'
    out['util'][failure]=np.nan
    out['status'][pending & ~failure]=np.array([str(v) if '6.109 não demonstrado' in str(v) else str(v)+'; 6.109 não demonstrado noutra situação' for v in out['status'][pending & ~failure]],dtype=object)
    out['transfer_status'][transfer]='LL.115: corte adicional por verificar (gradiente espacial)'
    out['envelope_count']=count
    out['allowance_complete']=~missing
    out['intact_candidate'] &= ~missing
    out['intact_status']=np.where(out['intact_candidate'],'LL(103/107): alternativa elástica; confirmar secção íntegra','Via elástica não demonstrada; manter sandwich fendilhado')
    return out


def refine(d,provisional,adopted):
    if not d.optimize_rebar or d.axial_convention=='Não definida':return
    sign=1 if d.axial_convention=='Tracção positiva' else -1
    for panel,g in provisional[provisional.tensor_ok&provisional.shear_ok].groupby('Panel'):
        mesh=adopted[str(panel)]
        n=sign*g[['NXX','NYY','NXY']].to_numpy(float);m=g[['MXX','MYY','MXY']].to_numpy(float);q=g[['QXX','QYY']].to_numpy(float)
        for _ in range(4):
            try:r=assess_envelope(d,mesh,n,m,q,strip_allowances(d,mesh,g))
            except ValueError:break
            changed=False
            for j,k in enumerate(LABELS):
                req=r['As_req_'+k];finite=req[np.isfinite(req)]
                if not len(finite) or finite.max()<=mesh[j].as_prov+1e-6:continue
                vertical=(j//2==int(d.local_y_is_vertical))
                try:c=d.optimize_rebar_solution(finite.max()+1e-5,d.max_spacing_for_direction(vertical),vertical,k)
                except ValueError:continue
                if c.as_prov>mesh[j].as_prov+1e-6 and d.service_candidate_fits(mesh,j,c):
                    c.optimization_note+='; Anexo F + modelo sandwich';mesh[j]=c;changed=True
            if not changed:break


def strip_allowance_status(status_x, status_y, complete):
    """Coverage of the X/Y strip increments only; no shell stability check."""
    sx=pd.Series(status_x).astype(str);sy=pd.Series(status_y).astype(str)
    complete=np.asarray(complete,bool)
    if len(sx)!=len(sy) or complete.shape!=(len(sx),):
        raise ValueError('Cobertura de segunda ordem por faixa incompatível')
    known=sx.str.startswith(('Não requerida','Dispensada','Incluída')).to_numpy() & sy.str.startswith(('Não requerida','Dispensada','Incluída')).to_numpy()
    included=sx.str.startswith('Incluída').to_numpy() | sy.str.startswith('Incluída').to_numpy()
    out=np.full(len(sx),'Dados locais pendentes',dtype=object)
    out[known & complete]='Dispensada por faixa; imperfeições consideradas quando aplicáveis'
    out[known & complete & included]='Incluída por faixa na envolvente'
    return out


def attach(r,d):
    out=[]
    for panel,g in r.groupby('Panel',sort=False):
        e=g[g.Combo_type.eq('ELU')];valid=e[e.Tensor_complete.eq(True)&e.QXX_raw.notna()&e.QYY_raw.notna()]
        if d.axial_convention=='Não definida':valid=valid.iloc[0:0]
        cols=pd.DataFrame(index=g.index);cols['Sand_status']='Fora do âmbito ELU'
        cols.loc[e.index,'Sand_status']='Dados insuficientes'
        if len(valid):
            try:
                sign=1 if d.axial_convention=='Tracção positiva' else -1
                mesh=[g.iloc[0][k+'_rebar'] for k in LABELS]
                n=sign*valid[['NXX_kN_m','NYY_kN_m','NXY_kN_m']].to_numpy(float)
                m=valid[['MXX_kNm_m','MYY_kNm_m','MXY_kNm_m']].to_numpy(float)
                q=valid[['QXX_kN_m','QYY_kN_m']].to_numpy(float)
                extra=np.column_stack([np.where(valid[f'Stability_{a}_status'].str.startswith('Não requerida'),0.,np.where(valid[f'Stability_{a}_status'].str.startswith(('Dispensada','Incluída')),np.maximum(0.,valid[f'NM_{a}_MEd'].abs()-valid[[f'M{a.lower()}+_WA',f'M{a.lower()}-_WA']].max(axis=1)),np.nan)) for a in 'XY'])
                result=assess_envelope(d,mesh,n,m,q,extra)
                data=pd.DataFrame({'Sand_'+k:v for k,v in result.items()},index=valid.index)
                # Only local strip coverage is within the dimensioning scope.
                data['Sand_strip_order_status']=strip_allowance_status(valid['Stability_X_status'],valid['Stability_Y_status'],result['allowance_complete'])
                cols=cols.drop(columns='Sand_status').join(data);cols['Sand_status']=cols.Sand_status.fillna('Fora do âmbito ELU');cols.loc[e.index.difference(valid.index),'Sand_status']='Dados insuficientes'
                modal=valid.Case.astype(str).str.contains('CQC|SRSS',case=False,regex=True)
                cols.loc[valid.index[modal],'Sand_status']='Modal; sinais por confirmar; '+cols.loc[valid.index[modal],'Sand_status']
            except ValueError as exc:cols.loc[valid.index,'Sand_status']='Modelo indisponível: '+str(exc)
        out.append(cols)
    result=r.join(pd.concat(out).reindex(r.index))
    return result
