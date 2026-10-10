#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare lossless app exports to FFmpeg LUT + independent OCIO CPU basic grade.

Usage: python check_grade_moving.py neutral.mp4 colored.mp4 lut.cube output_dir
Requires FFmpeg on PATH, numpy, opencolorio==2.4.2. Fixed prototype controls:
brightness .12, contrast .18, shadows .3, highlights -.4, exposure .37,
saturation .23, warmth .41, tint -.27. Streams all frames.
"""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np
from check_grade_reference import reference


def read_frame(pipe, size):
    data = bytearray()
    while len(data) < size:
        part = pipe.read(size - len(data))
        if not part: break
        data.extend(part)
    if data and len(data) != size: raise RuntimeError("Incomplete decoded frame")
    return data


def probe(media):
    return json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_streams", "-show_frames", "-show_format", "-of", "json", str(media)]))


def main():
    neutral, colored, lut, output = (Path(x).resolve() for x in sys.argv[1:5])
    output.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(lut, output / "reference.cube")
    n, c = probe(neutral), probe(colored)
    stream = n['streams'][0]
    w,h = stream['width'],stream['height']
    keys=['width','height','pix_fmt','r_frame_rate','color_space','color_range','color_transfer','color_primaries']
    if any(stream.get(k)!=c['streams'][0].get(k) for k in keys): raise RuntimeError("Stream properties differ")
    if stream['pix_fmt']!='yuv420p10le': raise RuntimeError("Expected ten-bit lossless exports")
    timestamps=lambda p:[(f.get('best_effort_timestamp'),f.get('duration')) for f in p['frames']]
    if timestamps(n)!=timestamps(c): raise RuntimeError("Frame count or timestamps differ")
    comment=c.get('format',{}).get('tags',{}).get('comment','')
    if 'GyroGrade basic grade v1:' not in comment: raise RuntimeError("Missing tone export marker")
    filters=f"format=gbrpf32le,lut3d=file=reference.cube:interp=tetrahedral"
    logs=[(output/f'{name}.log').open('wb') for name in ['input','conversion','colored']]
    base=['ffmpeg','-v','error','-xerror','-threads','1']
    source=subprocess.Popen(base+['-i',str(neutral),'-an','-vf',filters,'-pix_fmt','gbrpf32le','-f','rawvideo','pipe:1'],cwd=output,stdout=subprocess.PIPE,stderr=logs[0])
    convert=subprocess.Popen(base+['-f','rawvideo','-pixel_format','gbrpf32le','-video_size',f'{w}x{h}',
        '-framerate',stream['r_frame_rate'],'-i','pipe:0','-an','-vf','scale=out_color_matrix=bt709:out_range=limited,format=yuv420p10le',
        '-pix_fmt','yuv420p10le','-f','rawvideo','pipe:1'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=logs[1])
    actual=subprocess.Popen(base+['-i',str(colored),'-an','-pix_fmt','yuv420p10le','-f','rawvideo','pipe:1'],stdout=subprocess.PIPE,stderr=logs[2])
    controls=(.12,.18,.3,-.4,.37,.23,.41,-.27)
    def feed():
        count=0
        try:
            while data:=read_frame(source.stdout,w*h*12):
                planar=np.frombuffer(data,'<f4').reshape(3,h,w)
                # GBR planes to packed RGB for the independent library.
                rgb=np.stack([planar[2],planar[0],planar[1]],axis=2)
                rgb=reference(rgb,controls)
                convert.stdin.write(np.stack([rgb[:,:,1],rgb[:,:,2],rgb[:,:,0]]).astype('<f4').tobytes())
                count+=1
        finally: convert.stdin.close()
        if source.wait()!=0: raise RuntimeError("Reference source decode failed")
        return count
    frames=0; maximum=0; changed=0; total=0
    with ThreadPoolExecutor(max_workers=1) as pool:
        feeding=pool.submit(feed)
        while ref_frame:=read_frame(convert.stdout,w*h*3):
            decoded=read_frame(actual.stdout,w*h*3)
            if not decoded: raise RuntimeError("Colored export ended early")
            delta=np.abs(np.frombuffer(ref_frame,'<u2').astype(np.int32)-np.frombuffer(decoded,'<u2').astype(np.int32))
            maximum=max(maximum,int(delta.max()));changed+=int(np.count_nonzero(delta));total+=len(delta);frames+=1
        fed=feeding.result(timeout=30)
    if read_frame(actual.stdout,w*h*3): raise RuntimeError("Colored export has extra frames")
    if convert.wait()!=0 or actual.wait()!=0: raise RuntimeError("Full decoding/conversion failed")
    if fed!=frames or frames!=len(n['frames']): raise RuntimeError("Frame count mismatch")
    if maximum>1: raise RuntimeError(f"Independent OCIO reference differs by {maximum} ten-bit codes")
    report=dict(frames=frames,timestamps_equal=True,stream_properties_equal=True,full_decode=True,
                max_10bit_code_error=maximum,changed_samples=changed,total_samples=total,
                independent_reference='FFmpeg tetrahedral LUT + OCIO 2.4.2 CPU',tone_marker=True)
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__': main()
