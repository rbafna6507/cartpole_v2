"""MJCF construction with explicit pendulum inertial properties."""
from .config import RigConfig


def model_xml(config: RigConfig) -> str:
    """Return the model; visible geometry does not silently define its inertia.

    I_pivot = m*d*L_eff and the parallel-axis theorem gives I_COM.
    The tiny axial inertia and equal transverse moments form a physically
    admissible tensor while preserving the fitted y-axis rotational inertia.
    """
    mass = config.total_pendulum_mass_kg
    inertia = config.pivot_inertia_kg_m2
    transverse = inertia - mass * config.com_m**2
    if transverse <= 0:
        raise ValueError("effective length must exceed COM distance")
    axial = min(transverse, mass * (0.003**2) / 2)
    cart_inertia = config.cart_mass_kg * 0.001
    return f'''<mujoco model="deployment_cartpole">
  <compiler angle="radian" inertiafromgeom="false"/>
  <option timestep="{config.control_dt_s:.17g}" gravity="0 0 -9.81" integrator="RK4"/>
  <default><geom contype="0" conaffinity="0"/></default>
  <visual><global azimuth="90" elevation="-15"/></visual>
  <worldbody>
    <light pos="0 -1 2"/>
    <geom name="rail" type="box" pos="0 0 0.03" size="{config.rail_half_m:.17g} 0.012 0.008" rgba="0.3 0.35 0.4 1"/>
    <body name="cart" pos="0 0 0.07">
      <inertial pos="0 0 0" mass="{config.cart_mass_kg:.17g}" diaginertia="{cart_inertia:.17g} {cart_inertia:.17g} {cart_inertia:.17g}"/>
      <joint name="cart_slide" type="slide" axis="1 0 0" limited="true" range="{-config.rail_half_m:.17g} {config.rail_half_m:.17g}"/>
      <geom name="cart_geom" type="box" size="0.025 0.02 0.015" rgba="0.2 0.45 0.8 1"/>
      <body name="pendulum">
        <inertial pos="0 0 {config.com_m:.17g}" mass="{mass:.17g}" diaginertia="{transverse:.17g} {transverse:.17g} {axial:.17g}"/>
        <joint name="pendulum_hinge" type="hinge" axis="0 1 0" damping="{inertia * config.damping_per_s:.17g}" frictionloss="{inertia * config.coulomb_rad_s2:.17g}"/>
        <geom name="arm" type="capsule" fromto="0 0 0 0 0 {config.arm_length_m:.17g}" size="0.003" rgba="0.85 0.7 0.25 1"/>
        <geom name="tip_mass" type="sphere" pos="0 0 {config.arm_length_m:.17g}" size="0.006" rgba="0.7 0.2 0.15 1"/>
        <site name="tip" pos="0 0 {config.arm_length_m:.17g}" size="0.001"/>
      </body>
    </body>
  </worldbody>
  <equality>
    <joint name="cart_clamp" joint1="cart_slide" polycoef="0 0 0 0 0" active="false" solref="0.002 1" solimp="0.9999 0.9999 0.001"/>
  </equality>
  <actuator>
    <motor name="cart_force" joint="cart_slide" gear="1" ctrllimited="true" ctrlrange="{-config.actuator_force_limit_n:.17g} {config.actuator_force_limit_n:.17g}"/>
  </actuator>
</mujoco>'''


def build_model(config: RigConfig):
    """Compile headlessly; importing this module starts no viewer or device."""
    import mujoco

    return mujoco.MjModel.from_xml_string(model_xml(config))
