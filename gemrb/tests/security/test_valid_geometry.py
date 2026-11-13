#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
# SPDX-License-Identifier: GPL-2.0-or-later
"""Ordinary circle/ellipse point sequences and one-pixel light compatibility.

Compiles actual Geometry.cpp and Region.cpp, compares defined legacy cases
and an arbitrary-precision mathematical reference. No malformed probes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

def function(text,signature):
    start=text.index(signature)
    opening=text.index('{',start)
    depth,end=1,opening+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}')
        end+=1
    return text[start:end]

def circle(x0,y0,r,mask=255):
    points=[]
    def emit(x,y):
        octants=[(y,x),(-y,x),(x,y),(-x,y),(x,-y),(-x,-y),(y,-x),(-y,-x)]
        points.extend((x0+dx,y0+dy) for i,(dx,dy) in enumerate(octants) if mask&(1<<i))
    x,y,fm,de,dse=0,r,1-r,3,5-2*r
    emit(x,y)
    while x<y:
        if fm<=0: fm+=de
        else:
            fm+=dse
            dse+=2
            y-=1
        de+=2
        dse+=2
        x+=1
        emit(x,y)
    return points

def ellipse(x,y,w,h):
    if w==h:
        return circle(x+w//2,y+h//2,max(0,w//2-1))
    x1,y1,x2,y2=x,y,x+w-1,y+h-1
    a,b=x2-x1,y2-y1
    parity=b&1
    dx=4*(1-a)*b*b
    dy=4*(parity+1)*a*a
    err=dx+dy+parity*a*a
    y1+=(b+1)//2
    y2=y1-parity
    a_step,b_step=8*a*a,8*b*b
    points=[]
    while True:
        points.extend([(x2,y1),(x1,y1),(x1,y2),(x2,y2)])
        e2=2*err
        if e2<=dy:
            y1+=1
            y2-=1
            dy+=a_step
            err+=dy
        if e2>=dx or 2*err>dy:
            x1+=1
            x2-=1
            dx+=b_step
            err+=dx
        if x1>x2:break
    while y1-y2<b:
        points.extend([(x1-1,y1),(x2+1,y1),(x1-1,y2),(x2+1,y2)])
        y1+=1
        y2-=1
    return points

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--header-root',type=Path)
    parser.add_argument('--config-directory',type=Path,required=True)
    parser.add_argument('--baseline-root',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[3]
    headers=args.header_root or root
    source=(root/'gemrb/core/Geometry.cpp').read_text()
    baseline=(args.baseline_root/'gemrb/core/Geometry.cpp').read_text()
    old_circle=function(baseline,'std::vector<BasePoint> PlotCircle(')
    old_circle=old_circle.replace('PlotCircle(','LegacyCircle(').replace('uint8_t octants)','uint8_t octants = 0xff)')
    old_ellipse=function(baseline,'std::vector<BasePoint> PlotEllipse(')
    old_ellipse=old_ellipse.replace('PlotEllipse(','LegacyEllipse(').replace('PlotCircle(','LegacyCircle(')
    light=(root/'gemrb/core/Light.cpp').read_text()
    old_light=(args.baseline_root/'gemrb/core/Light.cpp').read_text()
    program=r'''
#include <cmath>
#include "Geometry.h"
#include "Video/ImageBufferSize.h"
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <string>
#include <vector>
namespace GemRB {
@LEGACY_CIRCLE@
@LEGACY_ELLIPSE@
template<class T> using Holder=std::shared_ptr<T>;
struct Sprite2D {
    Region Frame;
    uint8_t* pixels;
    Sprite2D(const Region& r,uint8_t* p):Frame(r),pixels(p){}
    ~Sprite2D(){free(pixels);}
};
struct PixelFormat { static PixelFormat Paletted8Bit(int,bool,int){return {};} };
struct FixtureVideo {
    Holder<Sprite2D> CreateSprite(const Region& r,void* p,PixelFormat){return std::make_shared<Sprite2D>(r,static_cast<uint8_t*>(p));}
};
FixtureVideo video;
FixtureVideo* VideoDriver=&video;
int GetLightPalette(){return 0;}
template<class T> T Clamp(T value,T low,T high){return std::min(high,std::max(low,value));}
@LIGHT@
@OLD_LIGHT@
}
using namespace GemRB;
int main(int argc,char** argv)
{
    if(std::string(argv[1])=="light"){
        for(auto intensity:{uint8_t(0),uint8_t(64),uint8_t(255)}){
            auto single=CreateLight(Size(1,1),intensity);
            assert(single && single->pixels[0]==intensity);
        }
        for(auto size:{Size(8,6),Size(10,10)}){
            auto actual=CreateLight(size,128);
            auto original=BaselineCreateLight(size,128);
            assert(std::equal(actual->pixels,actual->pixels+size.Area(),original->pixels));
        }
        auto moderate=CreateLight(Size(640,480),128);
        assert(moderate && moderate->pixels[240*640+320]==128);
        assert(moderate->pixels[240*640+620]==8); // floor(hypot(300,0)) stays300
        assert(moderate->pixels[315*640+420]==78); // floor(hypot(100,75)) is125
        assert(std::all_of(moderate->pixels,moderate->pixels+640*480,[](uint8_t value){return value<=128;}));
        std::cout<<"6 ordinary light fixtures passed\n";
        return 0;
    }
    assert(argc==7);
    int x=std::stoi(argv[2]),y=std::stoi(argv[3]),w=std::stoi(argv[4]),h=std::stoi(argv[5]),mask=std::stoi(argv[6]);
    std::vector<BasePoint> points;
    if(std::string(argv[1])=="circle"){
        points=PlotCircle(BasePoint(x,y),uint16_t(w),uint8_t(mask));
        assert(points==LegacyCircle(BasePoint(x,y),uint16_t(w),uint8_t(mask)));
    }else{
        points=PlotEllipse(Region(x,y,w,h));
        if(std::string(argv[1])=="legacy")assert(points==LegacyEllipse(Region(x,y,w,h)));
    }
    std::cout<<points.size()<<'\n';
    for(const auto& point:points)std::cout<<point.x<<' '<<point.y<<'\n';
}
'''.replace('@LEGACY_CIRCLE@',old_circle).replace('@LEGACY_ELLIPSE@',old_ellipse)
    program=program.replace('@LIGHT@',function(light,'Holder<Sprite2D> CreateLight('))
    program=program.replace('@OLD_LIGHT@',function(old_light,'Holder<Sprite2D> CreateLight(').replace('CreateLight(','BaselineCreateLight('))
    fixtures=[
        ('legacy',0,0,12,8,255),('legacy',-5,7,31,18,255),
        ('legacy',5,-8,2,9,255),('legacy',0,0,9,2,255),
        ('legacy',0,0,1,5,255),('legacy',2,3,2,2,255),
        ('legacy',0,0,20,20,255),('ellipse',0,0,1,1,255),
        ('ellipse',0,0,1500,900,255),('ellipse',7,11,131074,131074,255),
        ('circle',10,-4,0,0,255),('circle',10,-4,1,0,255),
        ('circle',10,-4,8,0,255),('circle',10,-4,25,0,37),
    ]
    cases=[]
    with tempfile.TemporaryDirectory(prefix='gemrb-valid-geometry-') as directory:
        cpp,binary=Path(directory)/'geometry.cpp',Path(directory)/'geometry'
        cpp.write_text(program)
        command=['g++','-std=c++14','-O1','-g','-DFMT_HEADER_ONLY',
                 '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                 '-I',str(args.config_directory),'-I',str(root/'gemrb/core'),
                 '-I',str(headers/'gemrb/core'),'-I',str(headers/'gemrb/includes'),
                 str(cpp),str(root/'gemrb/core/Geometry.cpp'),str(headers/'gemrb/core/Region.cpp'),
                 '-o',str(binary)]
        built=subprocess.run(command,capture_output=True,text=True,timeout=60)
        if built.returncode:
            print((built.stdout+built.stderr)[-7000:])
            raise SystemExit(built.returncode)
        for mode,x,y,w,h,mask in fixtures:
            run=subprocess.run([str(binary),mode,str(x),str(y),str(w),str(h),str(mask)],
                               capture_output=True,text=True,timeout=20)
            if run.returncode:raise RuntimeError(run.stderr[-4000:])
            values=[int(value) for value in run.stdout.split()]
            count=values[0]
            actual=list(zip(values[1::2],values[2::2]))
            expected=circle(x,y,w,mask) if mode=='circle' else ellipse(x,y,w,h)
            assert count==len(actual) and actual==expected,(mode,x,y,w,h,count,len(expected))
            cases.append({'mode':mode,'origin':[x,y],'size_or_radius':[w,h],'points':count})
        run=subprocess.run([str(binary),'light'],capture_output=True,text=True,timeout=20)
        if run.returncode:raise RuntimeError(run.stderr[-4000:])
        print(run.stdout,end='')
    print(str(len(cases))+' ordinary geometry point-sequence fixtures passed')
    report={'passed':len(cases)+6,'total':len(cases)+6,'geometry_cases':cases,
            'light_cases':'3 one-pixel intensities,2 ordinary pixel-identical baseline sizes,1 moderate640x480 light with defined distances beyond255',
            'source_sha256':{'gemrb/core/Geometry.cpp':hashlib.sha256(source.encode()).hexdigest(),
                             'gemrb/core/Light.cpp':hashlib.sha256(light.encode()).hexdigest()},
            'scope':'Actual Geometry.cpp and Region.cpp with real headers; actual CreateLight body uses narrow palette/factory stand-ins. Exact ordered legacy-safe and arbitrary-precision reference comparisons.',
            'limits':'No malformed inputs, overflow rejection probes, allocation-failure injection, full renderer, engine link or visual acceptance.'}
    if args.output:args.output.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':
    main()
