import json, re, math, sys
src = sys.argv[1]; conn = sys.argv[2]; out = sys.argv[3]
V=[];F=[]
for line in open(src):
    p=line.split()
    if not p: continue
    if p[0]=='v': V.append([float(x) for x in p[1:4]])
    elif p[0]=='f': F.append([int(t.split('/')[0])-1 for t in p[1:4]])
assert len(V)==468, len(V)
# normalise: centre and scale so that face height ~ 2 units
xs=[v[0] for v in V]; ys=[v[1] for v in V]; zs=[v[2] for v in V]
cx=(max(xs)+min(xs))/2; cy=(max(ys)+min(ys))/2; cz=(max(zs)+min(zs))/2
s=2.0/(max(ys)-min(ys))
Vn=[[(v[0]-cx)*s,(v[1]-cy)*s,(v[2]-cz)*s] for v in V]
# normals
N=[[0,0,0] for _ in V]
for a,b,c in F:
    A,B,C=Vn[a],Vn[b],Vn[c]
    u=[B[i]-A[i] for i in range(3)]; w=[C[i]-A[i] for i in range(3)]
    n=[u[1]*w[2]-u[2]*w[1],u[2]*w[0]-u[0]*w[2],u[0]*w[1]-u[1]*w[0]]
    for k in (a,b,c):
        for i in range(3): N[k][i]+=n[i]
def nz(n):
    l=math.sqrt(sum(x*x for x in n)) or 1
    return [x/l for x in n]
N=[nz(n) for n in N]
# ensure normals point outward (+z for front)
if sum(n[2] for n in N)<0: N=[[-x for x in n] for n in N]
txt=open(conn).read()
def grab(name):
    m=re.search(name+r'\s*=\s*frozenset\(\[(.*?)\]\)', txt, re.S)
    return [list(map(int,t)) for t in re.findall(r'\((\d+),\s*(\d+)\)', m.group(1))]
groups={k:grab('FACEMESH_'+k) for k in ['LIPS','LEFT_EYE','RIGHT_EYE','LEFT_EYEBROW','RIGHT_EYEBROW','FACE_OVAL','NOSE']}
tess=grab('FACEMESH_TESSELATION')
edges=sorted({tuple(sorted(e)) for e in tess})
r=lambda x: round(x,4)
data={
 "source":"MediaPipe canonical_face_model.obj + face_mesh_connections.py (google-ai-edge/mediapipe, Apache-2.0)",
 "count":len(Vn),
 "vertices":[r(c) for v in Vn for c in v],
 "normals":[round(c,3) for n in N for c in n],
 "triangles":[i for f in F for i in f],
 "edges":[i for e in edges for i in e],
 "contours":{k.lower():[i for e in v for i in e] for k,v in groups.items()},
}
json.dump(data, open(out,'w'), separators=(',',':'))
print(len(Vn), len(F), len(edges), {k:len(v) for k,v in groups.items()})
print('x',min(v[0] for v in Vn),max(v[0] for v in Vn),'y',min(v[1] for v in Vn),max(v[1] for v in Vn),'z',min(v[2] for v in Vn),max(v[2] for v in Vn))
