"""Merges the web check of the optional unsure rows (scratchpad results) into faculty_to_verify_updated.csv."""
import json, pandas as pd
S="/tmp/claude-1000/-home-Tj-Desktop-semesters-SEM7-dpcn-DPCN-Assignment-2/e93c3c2d-19e5-4541-85d8-498616df45b1/scratchpad"
t=pd.read_pickle(S+"/opt_targets.pkl").reset_index(drop=True)
res={}
for l in open(S+"/opt_results.jsonl"):
    r=json.loads(l); res[r["i"]]=r
d=pd.read_csv("faculty_to_verify_updated.csv",dtype=str,keep_default_na=False)
print(len(t),len(res),set(range(len(t)))-set(res))
cnt={};miss=0
for i,x in t.iterrows():
    m=d[(d.institution==x.institution)&(d.name==x["name"])&(d.reasons==x.reasons)&(d.verified=="unsure")&(d.checked_by=="auto: no decisive evidence")]
    if len(m)!=1: miss+=1; print("no unique row",i,x["name"],len(m)); continue
    r=res[i]; j=m.index[0]
    d.loc[j,["verified","notes","checked_by"]]=[r["v"],r["n"],"web: institute page / Vidwan / ORCID"]
    cnt[r["v"]]=cnt.get(r["v"],0)+1
d.to_csv("faculty_to_verify_updated.csv",index=False)
print(cnt,"miss",miss); print(d.verified.value_counts().to_dict())
