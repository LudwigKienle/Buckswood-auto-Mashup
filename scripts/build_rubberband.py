"""Build the pinned upstream single-file library against macOS Accelerate."""
import json
import subprocess
from pathlib import Path
from studio.storage import DATA

REVISION='1d95888bec3ae0a17c0c4af791810d5a63f6bc35'
source=DATA/'rubberband-source'
build=DATA/'rubberband-build'
build.mkdir(exist_ok=True)
if not source.exists():
    subprocess.run(['git','clone','--branch','v4.0.0','--depth','1','https://github.com/breakfastquay/rubberband.git',str(source)],check=True)
actual=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
if actual!=REVISION:
    subprocess.run(['git','-C',str(source),'fetch','--depth','1','origin',REVISION],check=True)
    subprocess.run(['git','-C',str(source),'checkout',REVISION],check=True)
target=build/'librubberband.next.dylib'
subprocess.run(['clang++','-O3','-std=c++11','-dynamiclib',str(source/'single/RubberBandSingle.cpp'),'-framework','Accelerate','-o',str(target)],check=True)
target.replace(build/'librubberband.dylib')
(build/'version.json').write_text(json.dumps({'version':'4.0.0','revision':REVISION}))
print('Rubber Band 4.0.0 bereit')
