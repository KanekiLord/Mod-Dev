"""Sprite restoration from user-supplied 128x128 PNGs.

Removes extraneous frame pixels in the corners only. Never scales, redraws, or
modifies facial features. Run once when generating the release; runtime has no
Pillow/numpy/cv2 dependency. Original files are copied to originais_backup.
"""
from pathlib import Path
from shutil import copy2
from collections import deque
from PIL import Image

BASE=Path(__file__).resolve().parents[1]/'mascotes'/'kaguya'

def repair_one(path:Path, expression:bool):
    im=Image.open(path).convert('RGBA')
    if im.size!=(128,128):raise ValueError(f'{path.name}: dimensões inesperadas {im.size}')
    backup=BASE/'originais_backup'/path.parent.name/path.name
    backup.parent.mkdir(parents=True,exist_ok=True)
    if not backup.exists():copy2(path,backup)
    px=im.load(); removed=set()
    def flood(sx,sy):
        if px[sx,sy][3]==0:return
        cx=0 if sx==0 else 127; cy=0 if sy==0 else 127
        q=deque([(sx,sy)]);done=set(); component=set()
        while q:
            x,y=q.popleft()
            if (x,y) in done:continue
            done.add((x,y))
            if abs(x-cx)>13 or abs(y-cy)>13:continue
            r,g,b,a=px[x,y]
            if not a or max(r,g,b)>115:continue
            component.add((x,y))
            if x>0:q.append((x-1,y))
            if x<127:q.append((x+1,y))
            if y>0:q.append((x,y-1))
            if y<127:q.append((x,y+1))
        # Frame-origin corner fragments should be dark and within 14px of a corner.
        for pos in component:
            px[pos]=(*px[pos][:3],0)
            removed.add(pos)
    flood(0,0);flood(127,0)
    if expression:
        flood(0,127);flood(127,127)
        # Exact frame endpoints: transparent even if a tinted artifact remains.
        for x,y in ((0,0),(127,0),(0,127),(127,127)):
            if px[x,y][3]:
                px[x,y]=(*px[x,y][:3],0);removed.add((x,y))
    else:
        # Animation frames include a horizontal, opaque decorative border along
        # their top edge which is not part of the woman's hair.
        for y in range(0,2):
            for x in range(128):
                if px[x,y][3] and (y==0 or x<22 or x>110):
                    px[x,y]=(*px[x,y][:3],0);removed.add((x,y))
        for x in (0,127):
            for y in range(0,3):px[x,y]=(*px[x,y][:3],0)
    # Remove isolated single-pixel leftovers of the original rounded frame.
    visited=set()
    for yy in range(128):
        for xx in range(128):
            if (xx,yy) in visited or px[xx,yy][3]==0:continue
            q=deque([(xx,yy)]);cc=set()
            while q:
                x,y=q.popleft()
                if (x,y) in visited or not(0<=x<128 and 0<=y<128):continue
                visited.add((x,y))
                if px[x,y][3]==0:continue
                cc.add((x,y))
                q.extend(((x-1,y),(x+1,y),(x,y-1),(x,y+1)))
            # Small leftovers near corners only. Do not delete distant icons.
            corner=any((x<11 or x>116) and (y<12 or y>116) for x,y in cc)
            if corner and len(cc)<=24:
                for x,y in cc:
                    px[x,y]=(*px[x,y][:3],0)
                    removed.add((x,y))
    if not expression:
        # Horizontal top-border leftovers. Hair starts near the center;
        # retain that zone while clearing the disjoint straight line.
        for y in (1,2):
            for x in list(range(0,55))+list(range(95,128)):
                if px[x,y][3]:
                    px[x,y]=(*px[x,y][:3],0)
                    removed.add((x,y))
    im.save(path)
    return len(removed)

if __name__=='__main__':
    count=0
    for kind in ('expressoes','animacoes'):
        for file in sorted((BASE/kind).glob('*.png')):
            n=repair_one(file,kind=='expressoes')
            count+=1
            print(f'{file.name}: {n} pixels de moldura removidos')
    print(f'Reparados {count} sprites. Originais em originais_backup.')
