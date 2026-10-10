#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pinned OCIO CPU reference versus native frames and production Metal QSB.
Usage: python check_grade_reference.py grade_fixture qml output_dir [lut.cube] [--cpu-only]
Requires opencolorio==2.4.2, numpy, Pillow and FFmpeg. Synthetic data only.
Gamma-2.4 display-linear exposure is intentionally not camera RAW exposure.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np
import PyOpenColorIO as ocio
from PIL import Image
from generate_tone_tables import processor as tone_processor


def balance_processor(exposure, warmth, tint):
    if ocio.__version__ != '2.4.2': raise RuntimeError('Use pinned OCIO 2.4.2')
    stops = np.array([.75*warmth+.25*tint, -.5*tint, -.75*warmth+.25*tint])
    norm = np.dot(np.exp2(stops), [.2126,.7152,.0722])
    value = ocio.GradingPrimary(ocio.GRADING_LIN)
    value.exposure = ocio.GradingRGBM(*stops, exposure-np.log2(norm))
    primary = ocio.GradingPrimaryTransform(ocio.GRADING_LIN); primary.setValue(value)
    group = ocio.GroupTransform()
    group.appendTransform(ocio.ExponentTransform(value=[2.4,2.4,2.4,1], negativeStyle=ocio.NEGATIVE_MIRROR))
    group.appendTransform(primary)
    group.appendTransform(ocio.ExponentTransform(value=[1/2.4,1/2.4,1/2.4,1], negativeStyle=ocio.NEGATIVE_MIRROR))
    return ocio.Config.CreateRaw().getProcessor(group).getOptimizedCPUProcessor(ocio.OPTIMIZATION_NONE)


def saturation_processor(amount):
    value = ocio.GradingPrimary(ocio.GRADING_VIDEO); value.saturation=1+amount
    transform = ocio.GradingPrimaryTransform(ocio.GRADING_VIDEO); transform.setValue(value)
    return ocio.Config.CreateRaw().getProcessor(transform).getDefaultCPUProcessor()


def reference(rgb, controls):
    b,c,s,h,e,sat,w,t = controls
    rgb=np.array(rgb,dtype=np.float32,copy=True)
    if e or w or t: balance_processor(e,w,t).applyRGB(rgb)
    rgb=np.clip((rgb.astype(np.float64)-.5)*(1+c)+.5+b,0,1).astype(np.float32)
    tone_processor(s,h).applyRGB(rgb)
    if sat: saturation_processor(sat).applyRGB(rgb)
    return np.clip(rgb,0,1)


def lut_reference(rgb, lut, output):
    shutil.copyfile(lut, output/'reference.cube')
    h,w,_=rgb.shape
    planar=np.stack([rgb[:,:,1],rgb[:,:,2],rgb[:,:,0]]).astype('<f4')
    raw=subprocess.check_output(['ffmpeg','-v','error','-xerror','-f','rawvideo','-pixel_format','gbrpf32le',
        '-video_size',f'{w}x{h}','-i','pipe:0','-vf','lut3d=file=reference.cube:interp=tetrahedral',
        '-pix_fmt','gbrpf32le','-f','rawvideo','-'],input=planar.tobytes(),cwd=output)
    p=np.frombuffer(raw,'<f4').reshape(3,h,w)
    return np.stack([p[2],p[0],p[1]],axis=2)


def main():
    cpu_only="--cpu-only" in sys.argv
    if cpu_only: sys.argv.remove("--cpu-only")
    fixture,qml,out=(Path(x).resolve() for x in sys.argv[1:4]);out.mkdir(parents=True,exist_ok=True)
    lut=Path(sys.argv[4]).resolve() if len(sys.argv)>4 else None
    root=Path(__file__).resolve().parents[2];rng=np.random.default_rng(7102026)
    w,h=1025,65
    rgba=rng.uniform(-.1,1.1,(h,w,4)).astype('<f4');rgba[0,:,:3]=np.linspace(0,1,w)[:,None]
    rgba[1,:8,:3]=np.array([[1,0,0],[0,1,0],[0,0,1],[1,1,1],[0,0,0],[.5,.5,.5],[-.1,-.1,-.1],[1.1,1.1,1.1]])
    rgba[:,:,3]=rng.uniform(0,1,(h,w));rgba.tofile(out/'input.f32')
    cases=[(0,0,0,0,e,0,0,0) for e in (-2,-.371,0,.419,2)]
    for field in range(5,8):
        for amount in (-1,-.317,.219,1):
            controls=[0]*8;controls[field]=amount;cases.append(tuple(controls))
    cases +=[(.12,.18,.3,-.4,.37,.23,.41,-.27),(-.5,.5,.5,-.5,-2,-1,-1,1),(.5,-.5,-.5,.5,2,1,1,-1)]
    results=[]
    def run_fixture(inputfile, controls, use_lut, width,height,copies):
        subprocess.run([str(fixture),str(inputfile),str(out/'actual.f32'),str(out/'tone.rgb'),str(width),str(height),
            *map(str,controls[:4]),str(copies),*map(str,controls[4:])] + ([str(lut)] if use_lut else []),check=True,timeout=30,capture_output=True)
    base_lut=lut_reference(rgba[:,:,:3],lut,out) if lut else None
    for use_lut in ([False,True] if lut else [False]):
        for controls in cases:
            run_fixture(out/'input.f32',controls,use_lut,w,h,3)
            actual=np.fromfile(out/'actual.f32','<f4').reshape(h,w,4)
            source=base_lut if use_lut else rgba[:,:,:3]
            expected=reference(source,controls) if any(controls) else source
            error=float(np.max(np.abs(expected-actual[:,:,:3])))
            if error>1e-5: raise RuntimeError(f'CPU OCIO mismatch {use_lut,controls}: {error}')
            if not np.array_equal(rgba[:,:,3],actual[:,:,3]): raise RuntimeError('Alpha changed')
            results.append(dict(controls=controls,lut=use_lut,float_max_error=error))
    if cpu_only:
        (out/'results.json').write_text(json.dumps(results,indent=2)+'\n')
        print(json.dumps(dict(cpu_cases=len(results),cpu_max_error=max(x['float_max_error'] for x in results),gpu_cases=0)))
        return
    rgb=rng.integers(0,256,(128,128,3),dtype=np.uint8);Image.fromarray(rgb).save(out/'input.png')
    prgba=np.ones((128,128,4),dtype='<f4');prgba[:,:,:3]=rgb/255;prgba.tofile(out/'preview.f32')
    template=(root/'tests/export-lut/preview-shader-check.qml').read_text()
    Image.new('RGB',(2,2)).save(out/'atlas.png');Image.new('RGB',(256,33)).save(out/'tone.png')
    gpu_cases=[cases[1],cases[4],cases[8],cases[-3],cases[-2],cases[-1]]
    for use_lut in ([False,True] if lut else [False]):
        base=lut_reference(prgba[:,:,:3],lut,out) if use_lut else prgba[:,:,:3]
        for i,controls in enumerate(gpu_cases):
            run_fixture(out/'preview.f32',controls,use_lut,128,128,1)
            size=0
            if use_lut:
                aw,ah,size=map(int,(out/'atlas-size.txt').read_text().split());Image.frombytes('RGB',(aw,ah),(out/'atlas.rgb').read_bytes()).save(out/'atlas.png')
            if any(controls[2:4]): Image.frombytes('RGB',(256,33),(out/'tone.rgb').read_bytes()).save(out/'tone.png')
            gains=json.loads((out/'gains.json').read_text())
            harness=template.replace('../../src/qt_gpu/compiled/color_preview.frag.qsb',(root/'src/qt_gpu/compiled/color_preview.frag.qsb').as_uri())
            for key,old,new in [('brightness',.1,controls[0]),('contrast',.2,controls[1]),('lutSize',33,size),('toneEnabled',0,int(any(controls[2:4]))),
                ('gradeRed',1,gains['gains'][0]),('gradeGreen',1,gains['gains'][1]),('gradeBlue',1,gains['gains'][2]),('gradeSaturation',1,gains['saturation'])]:
                harness=harness.replace(f'{key}: {old};',f'{key}: {new};')
            (out/'check.qml').write_text(harness)
            run=subprocess.run([str(qml),str(out/'check.qml')],cwd=out,env=dict(os.environ,QSG_RHI_BACKEND='metal',QSG_INFO='1'),capture_output=True,timeout=30)
            log=(run.stdout+run.stderr).decode(errors='replace');(out/f'gpu-{use_lut}-{i}.log').write_text(log)
            if run.returncode or 'Failed to' in log or 'compilation failed' in log: raise RuntimeError(log)
            actual=np.array(Image.open(out/'actual.png').convert('RGB').resize((128,128),Image.Resampling.NEAREST)).astype(int)
            expected=np.rint(reference(base,controls)*255).astype(int)
            error=int(np.max(np.abs(actual-expected)))
            if error>1: raise RuntimeError(f'Metal OCIO mismatch {use_lut,controls}: {error}')
            results.append(dict(gpu_controls=controls,lut=use_lut,rgb8_max_error=error,backend='Metal'))
    (out/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(dict(cpu_cases=sum('float_max_error' in x for x in results),cpu_max_error=max(x.get('float_max_error',0) for x in results),gpu_cases=sum('rgb8_max_error' in x for x in results),gpu_max_error=max(x.get('rgb8_max_error',0) for x in results))))


if __name__=='__main__': main()
