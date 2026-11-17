import re,sys
src=open('/app/data/levels/world2/walking_leaves.stl').read()
maps=[]
for m in re.finditer(r'\(tilemap(.*?)\(tiles\s*([\d\s]+)\)', src, re.S):
    head=m.group(1)
    if '(solid #t)' not in head: continue
    w=int(re.search(r'\(width (\d+)\)',head).group(1))
    t=list(map(int,m.group(2).split()))
    maps.append((w,t))
x0,x1,y0,y1=[int(a) for a in sys.argv[1:5]]
for y in range(y0,y1):
    row=''
    for x in range(x0,x1):
        c='.'
        for w,t in maps:
            v=t[y*w+x]
            if v: c='#' if c=='.' else c
        row+=c
    print('%2d %s'%(y,row))
