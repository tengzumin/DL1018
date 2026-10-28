import csv,json,math,hashlib,pathlib,collections
root=pathlib.Path.cwd(); base=root/'reports/attitude_cm18_a1_20261024/runtime_preparation_v1/screen4_same_state_replay_v6'; p=base/'screen4_event_records.csv'
groups=collections.defaultdict(list)
with p.open(newline='',encoding='utf-8-sig') as f:
 for row in csv.DictReader(f): groups[row['scene_id']].append(row)
out=[]
for sid,rows in groups.items():
 assert len(rows)==1999 and all(float(r['old_closure_pass'])==1 and float(r['new_action_evaluated'])==1 for r in rows)
 for label,rr in [('all',rows),('post5',[r for r in rows if float(r['event_time_s'])>=5])]:
  old=[math.sqrt(sum(float(r[f'old_E_omegaDot_minus_alphaBS_{a:02}'])**2 for r in rr)/len(rr)) for a in range(1,4)]
  new=[math.sqrt(sum(float(r[f'new_E_omegaDot_minus_alphaBS_{a:02}'])**2 for r in rr)/len(rr)) for a in range(1,4)]
  out.append(dict(scene_id=sid,period=label,n=len(rr),old_axis_rms=old,new_axis_rms=new,old_vector_rms=math.sqrt(sum(v*v for v in old)),new_vector_rms=math.sqrt(sum(v*v for v in new)),old_any_motor_sat=sum(any(float(r[f'old_motor_saturated_{a:02}']) for a in range(1,5)) for r in rr),new_any_motor_sat=sum(any(float(r[f'new_motor_saturated_{a:02}']) for a in range(1,5)) for r in rr),new_any_output_clip=sum(any(float(r[f'output_clipped_{a:02}']) for a in range(1,4)) for r in rr)))
report=dict(status='PASS_CSV_RECOMPUTATION',csv_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),rows=out,scope='same recorded state instantaneous acceleration mismatch; not integrated closed-loop performance')
q=root/'reports/attitude_cm18_a1_20261024/ROOT_SCREEN4_CSV_INDEPENDENT_REVIEW_v1.json';assert not q.exists();q.write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2))
