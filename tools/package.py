"""Package public source/runtime files, excluding caches, images and credentials."""
import argparse
from pathlib import Path
import tarfile

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('output',type=Path)
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
args.output.parent.mkdir(parents=True,exist_ok=True)
with tarfile.open(args.output,'w:gz') as archive:
    for name in ('README.md','LICENSE','THIRD_PARTY_NOTICES.md','AGENTS.md','.gitignore','.gitattributes','openapi.json','docs','examples','bridge','phone','tools','deploy','tests'):
        path=root/name
        for file in sorted(path.rglob('*')) if path.is_dir() else [path]:
            if file.is_file() and '__pycache__' not in file.parts and file.suffix!='.pyc':
                archive.add(file,arcname=str(file.relative_to(root)),recursive=False)
    xap=root/'build/LumiaAgent.xap'
    if xap.exists(): archive.add(xap,arcname='build/LumiaAgent.xap')
print(args.output.resolve())
