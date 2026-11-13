#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Contributors to the GemRB project <https://gemrb.org>
# SPDX-License-Identifier: GPL-2.0-or-later
"""Actual font blitter, real Glyph/Region headers, ordinary supported layouts.

No malformed glyph/file/allocation probes, full renderer or visual acceptance.
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

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--header-root',type=Path)
    parser.add_argument('--config-directory',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[3]
    headers=args.header_root or root
    source=(root/'gemrb/core/GUI/TextSystem/Font.cpp').read_text()
    region=(headers/'gemrb/core/Region.cpp').read_text()
    constructors='\n'.join(function(region,s) for s in [
        'BasePoint::BasePoint(int x, int y)',
        'Size::Size(int w, int h)'])
    blit=function(source,'static void BlitGlyphToCanvas(')
    program=r'''
#include "GUI/TextSystem/Font.h"
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <limits>
#include <vector>
namespace GemRB {
@CONSTRUCTORS@
@BLIT@
}
using namespace GemRB;
int main()
{
    {
        std::vector<ieByte> src{1,2,3,99,4,5,6,99};
        std::vector<ieByte> dst(20,0);
        Glyph g(Size(3,2),Point(0,0),src.data(),4,1);
        BlitGlyphToCanvas(g,Point(1,1),dst.data(),Size(5,4));
        std::vector<ieByte> expected(20,0);
        expected[6]=1;expected[7]=2;expected[8]=3;
        expected[11]=4;expected[12]=5;expected[13]=6;
        assert(dst==expected);
    }
    {
        std::vector<ieByte> src{1,2,3,99,4,5,6,99,7,8,9,99};
        std::vector<ieByte> dst(4,0);
        Glyph g(Size(3,3),Point(0,0),src.data(),4,1);
        BlitGlyphToCanvas(g,Point(-1,-1),dst.data(),Size(2,2));
        assert((dst==std::vector<ieByte>{5,6,8,9}));
    }
    {
        std::vector<ieByte> src(4*3*4);
        for(size_t i=0;i<src.size();++i)src[i]=static_cast<ieByte>(i+1);
        std::vector<ieByte> dst(5*4*4,0),expected(dst);
        Glyph g(Size(4,3),Point(0,0),src.data(),4,4);
        BlitGlyphToCanvas(g,Point(3,2),dst.data(),Size(5,4));
        for(size_t row=0;row<2;++row)
            std::copy_n(src.begin()+row*16,8,expected.begin()+((row+2)*5+3)*4);
        assert(dst==expected);
    }
    {
        std::vector<ieByte> src{7,8},dst(9,0);
        Glyph g(Size(2,1),Point(1,-1),src.data(),2,1);
        BlitGlyphToCanvas(g,Point(0,2),dst.data(),Size(3,3));
        assert(dst[4]==7 && dst[5]==8);
    }
    {
        std::vector<ieByte> src{1},dst(64,7);
        Glyph g(Size(1,1),Point(0,0),src.data(),1,1);
        BlitGlyphToCanvas(g,Point(10,10),dst.data(),Size(8,8));
        assert(std::all_of(dst.begin(),dst.end(),[](ieByte b){return b==7;}));
    }
    {
        std::vector<ieByte> dst(64,7);
        Glyph space(Size(3,0),Point(0,0),nullptr,3,1);
        BlitGlyphToCanvas(space,Point(0,0),dst.data(),Size(8,8));
        assert(std::all_of(dst.begin(),dst.end(),[](ieByte b){return b==7;}));
    }
    std::cout<<"6 ordinary font glyph-layout fixtures passed\n";
}
'''.replace('@CONSTRUCTORS@',constructors).replace('@BLIT@',blit)
    with tempfile.TemporaryDirectory(prefix='gemrb-valid-font-canvas-') as directory:
        cpp,binary=Path(directory)/'font.cpp',Path(directory)/'font'
        cpp.write_text(program)
        command=['g++','-std=c++14','-O1','-g','-fsanitize=address,undefined',
                 '-fno-sanitize-recover=all','-DFMT_HEADER_ONLY','-I',str(args.config_directory),
                 '-I',str(root/'gemrb/core'),'-I',str(headers/'gemrb/core'),
                 '-I',str(headers/'gemrb/includes'),str(cpp),'-o',str(binary)]
        compile_run=subprocess.run(command,capture_output=True,text=True,timeout=60)
        if compile_run.returncode:
            print((compile_run.stdout+compile_run.stderr)[-6000:])
            raise SystemExit(compile_run.returncode)
        run=subprocess.run([str(binary)],capture_output=True,text=True,timeout=20)
        print(run.stdout+run.stderr,end='')
    report={'passed':6 if run.returncode==0 else 0,'total':6,'exit_code':run.returncode,
            'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
            'header_sha256':hashlib.sha256((root/'gemrb/core/GUI/TextSystem/Font.h').read_text().encode()).hexdigest(),
            'actual_headers':['Font.h','Sprite2D.h','Region.h'],
            'scope':'Actual blitter and actual Region constructors with real project Glyph/Region headers; ordinary 1/4Bpp, padded pitch, clipped, positioned, offscreen and whitespace layouts.',
            'limits':'No malformed probes, fault injection, full engine/renderer or visual acceptance.'}
    if args.output:args.output.write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(run.returncode)
if __name__=='__main__':
    main()
