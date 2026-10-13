"""SI-unit N-link MJCF. theta=0 upright, positive leans +x; later angles relative.
Measured defaults: 100 mm rod, 11 g rod + 6 g tip screws, +/-200 mm travel.
Cart/drive/friction/camera defaults are UNMEASURED placeholders. No hardware I/O.
"""
import argparse
import json
import math

LINK_RGBA = ['0.85 0.25 0.20 1', '0.20 0.45 0.85 1', '0.95 0.75 0.15 1']


def link_properties(length=0.100, rod_mass=0.011, tip_mass=0.006,
                    tip_distance=None, rod_radius=0.002,
                    mass=None, com_dist=None, I_pivot=None):
    """Uniform slender cylinder + axial point mass, or measured mass/COM/inertia.
    Rod radius is a visual/axial-inertia approximation, not a measured dimension.
    Supplied I_pivot is about the hinge y axis; MJCF needs inertia about COM.
    """
    tip_distance = length if tip_distance is None else tip_distance
    if length <= 0 or rod_mass <= 0 or tip_mass < 0 or rod_radius <= 0 or tip_distance < 0:
        raise ValueError('Invalid rod geometry/mass')
    M = rod_mass + tip_mass
    c = (rod_mass * length / 2 + tip_mass * tip_distance) / M
    Ip = rod_mass * (length**2 / 3 + rod_radius**2 / 4) + tip_mass * tip_distance**2
    if any(v is not None for v in (mass, com_dist, I_pivot)):
        if not all(v is not None for v in (mass, com_dist, I_pivot)):
            raise ValueError('Measured mass, com_dist and I_pivot must be supplied together')
        M, c, Ip = mass, com_dist, I_pivot
    Ic = Ip - M*c*c
    Iz = rod_mass * rod_radius**2 / 2
    if not all(math.isfinite(v) for v in (M,c,Ip)) or M <= 0 or c <= 0 or Ic <= 0 or Iz > 2*Ic:
        raise ValueError('Nonphysical inertia: require I_pivot > mass*com_dist**2')
    return dict(mass=M, com_dist=c, I_pivot=Ip, I_com=Ic, I_axial=Iz,
                period=2*math.pi*math.sqrt(Ip/(M*9.81*c)))


def camera_distance(n_links, link_length, rail_limit, fovy=45., aspect=1.6, margin=.03):
    """Ideal perpendicular camera; rail_limit is HALF travel. Calibrate real lens."""
    if not 0 < fovy < 180 or aspect <= 0:
        raise ValueError('Invalid camera projection')
    reach = n_links*link_length
    return max(reach+margin, (rail_limit+reach+margin)/aspect)/math.tan(math.radians(fovy/2))


def make_mjcf(n_links=1, cart_mass=.5, link_length=.100, link_mass=.011,
              tip_mass=.006, tip_distance=None, joint_damping=0.,
              joint_frictionloss=0., rail_limit=.200, physical_rail_length=.500,
              v_max=.25, servo_kv=20., force_max=2., timestep=.0005,
              cam_fovy=45., cam_aspect=1.6, locked_cart=False,
              rail_limited=True, link_params=None, sysid=None):
    """link_mass means bare rod mass. link_params: per-link property overrides.
    sysid: single-link JSON from sysid_fit. Multi-link defaults repeat the first
    link only as a structural example; remeasure each actual link and joint.
    Velocity servo F=kv*(v_target-v) is an approximation, not a stepper model.
    Acceleration slew limiting belongs in the controller/env, not this actuator.
    """
    if n_links not in (1,2,3): raise ValueError('n_links must be 1, 2 or 3')
    if min(cart_mass,rail_limit,physical_rail_length,v_max,force_max,timestep) <= 0 or servo_kv < 0:
        raise ValueError('Invalid cart/drive settings')
    if link_params is not None and len(link_params) != n_links: raise ValueError('one config per link')
    if sysid is not None and n_links != 1: raise ValueError('sysid applies to single link only')
    configs=[]
    for i in range(n_links):
        p=dict(length=link_length, rod_mass=link_mass, tip_mass=tip_mass, tip_distance=tip_distance)
        extra=dict(link_params[i]) if link_params else {}
        damp=extra.pop('joint_damping', joint_damping)
        fric=extra.pop('joint_frictionloss', joint_frictionloss)
        p.update(extra)
        if sysid is not None:
            p.update({k:sysid[k] for k in ('mass','com_dist','I_pivot')})
            damp=sysid['joint_damping']; fric=sysid['joint_frictionloss']
        if min(damp,fric)<0: raise ValueError('Friction must be nonnegative')
        configs.append((p,link_properties(**p),damp,fric))
    reach=sum(p['length'] for p,_,_,_ in configs)
    dist=camera_distance(1,reach,rail_limit,cam_fovy,cam_aspect)
    slider='' if locked_cart else f'<joint name="slider" type="slide" axis="1 0 0" limited="{str(rail_limited).lower()}" range="{-rail_limit} {rail_limit}"/>'
    body=''
    for i,(p,b,damp,fric) in enumerate(configs):
        pos=0 if i==0 else configs[i-1][0]['length']
        body+=f'''<body name="link{i+1}" pos="0 0 {pos}">
          <joint name="hinge{i+1}" type="hinge" axis="0 1 0" damping="{damp}" frictionloss="{fric}"/>
          <inertial pos="0 0 {b['com_dist']}" mass="{b['mass']}" diaginertia="{b['I_com']} {b['I_com']} {b['I_axial']}"/>
          <geom name="pole{i+1}" type="capsule" fromto="0 0 0 0 0 {p['length']}" size="0.002" rgba="{LINK_RGBA[i]}"/>
          <geom name="tip{i+1}" type="sphere" pos="0 0 {p['length'] if p['tip_distance'] is None else p['tip_distance']}" size="0.005" rgba="{LINK_RGBA[i]}"/>
          <site name="endpoint{i+1}" pos="0 0 {p['length']}" size=".003"/>
'''
    body+='</body>'*n_links
    actuator='' if locked_cart else f'<actuator><velocity name="drive" joint="slider" kv="{servo_kv}" ctrllimited="true" ctrlrange="{-v_max} {v_max}" forcelimited="true" forcerange="{-force_max} {force_max}"/></actuator>'
    return f'''<mujoco model="cartpole{n_links}">
    <compiler inertiafromgeom="auto"/>
    <option timestep="{timestep}" integrator="RK4" gravity="0 0 -9.81"/>
    <default><joint limited="false"/><geom contype="0" conaffinity="0"/></default>
    <worldbody>
      <light pos="0 -1 1"/>
      <geom name="rail" type="capsule" fromto="{-physical_rail_length/2} 0 0 {physical_rail_length/2} 0 0" size=".008" rgba=".4 .4 .4 1"/>
      <body name="cart">{slider}
        <geom type="box" size=".025 .02 .015" mass="{cart_mass}" rgba=".25 .25 .28 1"/>
        {body}
      </body>
      <camera name="front" pos="0 {-dist} 0" xyaxes="1 0 0 0 0 1" fovy="{cam_fovy}"/>
    </worldbody>{actuator}</mujoco>'''


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('n_links',nargs='?',type=int,default=1)
    parser.add_argument('--sysid',help='fitted single-link params.json')
    args=parser.parse_args()
    fitted=None
    if args.sysid:
        with open(args.sysid) as f: fitted=json.load(f)
    print(make_mjcf(args.n_links,sysid=fitted))
