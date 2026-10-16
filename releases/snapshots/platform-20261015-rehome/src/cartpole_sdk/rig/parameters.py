"""Live tuning names, numeric limits and explicit host profile files.

No profile is loaded implicitly, and this module never opens a rig transport.
"""
from dataclasses import fields
import json
import math
from pathlib import Path
import struct
import tempfile
import os

from cartpole_sdk.contracts import ValidationError
from cartpole_sdk.control import ControllerParameters

PARAMETER_NAMES = tuple(field.name for field in fields(ControllerParameters))
# Lower bound, upper bound, whether the lower bound is inclusive.
_BOUNDS = {
    'leff':(.02,1,True), 'pw':(.1,30,True), 'bal_pw':(1,20,True),
    'pz':(.05,5,True), 'pc1':(-50,-.1,True), 'pc2':(-50,-.1,True),
    'vmax':(0,1.5,False), 'vmax_s':(0,1.5,False), 'vmax_b':(0,1.5,False),
    'approach_v':(0,1.5,False), 'catch_v':(0,1.5,False),
    'amax_s':(0,25,False), 'amax_b':(0,25,False), 'jmax':(0,150,False),
    'amax_m':(0,.5,False), 'jmax_m':(0,10,False), 'vman':(0,.15,True),
    'ke':(0,100,True), 'kpx':(0,1000,True), 'kdx':(0,100,True),
    'phase_soft':(0,50,False), 'catch_a':(.05,1.2,True),
    'catch_r':(.1,30,True), 'giveup':(.1,2.5,True), 'bw':(.1,100,True),
    'approach_angle':(.65,1.5,True), 'catch_da':(0,25,False),
    'spin_trip_rad_s':(0,150,False), 'spin_resume_rad_s':(0,150,False),
    'rail':(.02,.26,False),
}


def parameter_name(name):
    if not isinstance(name,str) or name not in PARAMETER_NAMES:
        raise ValidationError(f'unknown controller parameter: {name!r}')
    return name


def float32(value):
    return struct.unpack('f',struct.pack('f',value))[0]


def parameter_value(name,value):
    parameter_name(name)
    if isinstance(value,bool) or not isinstance(value,(int,float)):
        raise ValidationError(f'{name} must be finite numeric, not boolean')
    try:
        rounded=float32(value)
    except (OverflowError,struct.error):
        raise ValidationError(f'{name} must fit a finite float32') from None
    if not math.isfinite(rounded):
        raise ValidationError(f'{name} must be finite numeric')
    if value != 0 and (rounded == 0 or abs(rounded) < 2**-126):
        raise ValidationError(f'{name} must not underflow float32')
    lower,upper,inclusive=_BOUNDS[name]
    lower,upper=float32(lower),float32(upper)
    if rounded>upper or (rounded<lower if inclusive else rounded<=lower):
        relation='<=' if inclusive else '<'
        raise ValidationError(f'{name} requires {lower:g} {relation} value <= {upper:g}')
    return rounded


def parameter_map(values):
    if not isinstance(values,dict) or not values:
        raise ValidationError('profile parameters must be a nonempty object')
    return {parameter_name(name):parameter_value(name,value) for name,value in values.items()}


def validate_spin(values):
    if not 0 < values['spin_resume_rad_s'] < values['spin_trip_rad_s']:
        raise ValidationError('spin limits require 0 < spin_resume_rad_s < spin_trip_rad_s')


def read_profile(path):
    def unique(pairs):
        result={}
        for name,value in pairs:
            if name in result:raise ValidationError(f'duplicate profile key: {name}')
            result[name]=value
        return result
    try:
        document=json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=unique)
    except (ValueError,UnicodeError) as exc:
        raise ValidationError(f'invalid parameter profile: {exc}') from exc
    if not isinstance(document,dict) or type(document.get('schema_version')) is not int or document['schema_version']!=1:
        raise ValidationError('parameter profile requires schema_version 1')
    if set(document)-{'schema_version','parameters','source_firmware'}:
        raise ValidationError('unknown parameter profile fields')
    if 'source_firmware' in document and not isinstance(document['source_firmware'],str):
        raise ValidationError('source_firmware must be a string when supplied')
    return parameter_map(document.get('parameters'))


def write_profile(path,values,firmware=None):
    document={'schema_version':1,'parameters':values}
    if firmware is not None:document['source_firmware']=firmware
    destination=Path(path)
    pending=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=destination.parent,
                                         prefix=destination.name+'.',delete=False) as stream:
            pending=Path(stream.name)
            json.dump(document,stream,indent=2,sort_keys=True,allow_nan=False)
            stream.write('\n')
        os.replace(pending,destination)
    finally:
        if pending is not None and pending.exists():pending.unlink()
    return document
