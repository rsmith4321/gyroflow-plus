#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Official runtime CPU and generated Qt/Metal GPU proof; synthetic inputs only.

Usage: check_probe.py ocio_probe qsb qml output_directory
Requires the pinned development PyOpenColorIO 2.4.2 reference, numpy and Pillow.
This is not full-application or Windows acceptance.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image
import PyOpenColorIO as ocio

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/export-lut'))
from check_grade_reference import reference


def main():
    if ocio.__version__ != '2.4.2':
        raise RuntimeError('Use pinned OCIO 2.4.2')
    probe,qsb,qml,out=(Path(x).resolve() for x in sys.argv[1:])
    out.mkdir(parents=True,exist_ok=True)
    rng=np.random.default_rng(7112026)
    width,height=1025,65
    rgba=rng.uniform(-.1,1.1,(height,width,4)).astype('<f4')
    rgba[:,:,3]=rng.uniform(0,1,(height,width))
    rgba[0,:,:3]=np.linspace(0,1,width)[:,None]
    cases=[(0,)*8]
    for field,limit in enumerate((.5,.5,.5,.5,2,1,1,1)):
        for amount in (-limit,-.317*limit,.219*limit,limit):
            controls=[0]*8;controls[field]=amount;cases.append(tuple(controls))
    cases += [(.12,.18,.3,-.4,.37,.23,.41,-.27),
        (-.5,.5,.5,-.5,-2,-1,-1,1),(.5,-.5,-.5,.5,2,1,1,-1)]
    results=[]

    def run(pixels,controls,planar=False,baked=False):
        h,w,_=pixels.shape
        pixels.astype('<f4').tofile(out/'input.f32')
        proc=subprocess.run([str(probe),str(out/'input.f32'),str(out/'actual.f32'),
            str(out/'preview.frag'),str(w),str(h),'1',*map(str,controls)] + (['planar'] if planar else []) + (['baked'] if baked else []),
            capture_output=True,check=True,timeout=30)
        actual=np.fromfile(out/'actual.f32','<f4').reshape(h,w,4)
        if not np.array_equal(pixels[:,:,3],actual[:,:,3]):
            raise RuntimeError('Official processor changed alpha')
        return actual,json.loads(proc.stdout)

    for baked in (False,True):
        for planar in (False,True):
            for controls in cases:
                actual,timing=run(rgba,controls,planar,baked)
                expected=reference(rgba[:,:,:3],controls) if any(controls) else rgba[:,:,:3]
                error=float(np.max(np.abs(expected-actual[:,:,:3])))
                if error>1e-5: raise RuntimeError(f'Official processor/reference mismatch {baked,planar,controls}: {error}')
                results.append(dict(controls=controls,float_max_error=error,**timing))

    rgb=rng.integers(0,256,(128,128,3),dtype=np.uint8)
    Image.fromarray(rgb).save(out/'input.png')
    pixels=np.ones((128,128,4),dtype='<f4');pixels[:,:,:3]=rgb/255
    gpu_cases=[cases[0],cases[4],cases[8],cases[12],cases[16],cases[20],
        cases[24],cases[28],cases[32],*cases[-3:]]
    harness='''import QtQuick
import QtQuick.Window
Window {
 width:128; height:128; visible:true
 ShaderEffect {
  id:result; width:parent.width; height:parent.height
  property var source: Image { source:"input.png"; visible:false; smooth:false }
  fragmentShader:"preview.frag.qsb"
 }
 Timer { interval:300; running:true; onTriggered:result.grabToImage(function(image) {
  if (!image.saveToFile("actual.png")) console.error("Could not save shader result"); Qt.quit();
 }) }
}
'''
    (out/'check.qml').write_text(harness)
    for i,controls in enumerate(gpu_cases):
        cpu,_=run(pixels,controls)
        bake=subprocess.run([str(qsb),'--qt6','--glsl','300 es,330','--hlsl','50','--msl','12',
            '-o',str(out/'preview.frag.qsb'),str(out/'preview.frag')],capture_output=True,timeout=30)
        # qsb argv values are literal, not shell quoted.
        if bake.returncode:
            raise RuntimeError(bake.stderr.decode(errors='replace'))
        proc=subprocess.run([str(qml),str(out/'check.qml')],cwd=out,
            env=dict(os.environ,QSG_RHI_BACKEND='metal',QSG_INFO='1'),capture_output=True,timeout=30)
        log=(proc.stdout+proc.stderr).decode(errors='replace')
        (out/f'metal-{i}.log').write_text(log)
        if proc.returncode or 'Failed to' in log or 'compilation failed' in log or 'backend Metal' not in log:
            raise RuntimeError(log)
        image=Image.open(out/'actual.png').convert('RGB')
        if image.size not in ((128,128),(256,256),(384,384)):
            raise RuntimeError(f'Unexpected preview dimensions: {image.size}')
        scale=image.width//128
        actual=np.array(image.resize((128,128),Image.Resampling.NEAREST)).astype(int)
        expected=np.rint(np.clip(cpu[:,:,:3],0,1)*255).astype(int)
        error=int(np.max(np.abs(actual-expected)))
        if error>1: raise RuntimeError(f'OCIO Metal/CPU mismatch {controls}: {error}')
        results.append(dict(gpu_controls=controls,rgb8_max_error=error,backend='Metal',device_pixel_ratio=scale))
    report=dict(cpu_cases=4*len(cases),cpu_max_error=max(x.get('float_max_error',0) for x in results),
        gpu_cases=len(gpu_cases),gpu_max_error=max(x.get('rgb8_max_error',0) for x in results),
        ocio_version=ocio.__version__,results=results)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='results'}))


if __name__=='__main__': main()
