import pathlib,json,hashlib
import numpy as np
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
D=pathlib.Path(__file__).resolve().parent; source=D.parent/'ROOT_SCREEN12_PAIRED_METRICS_v1.json';data=json.loads(source.read_text());assert data['completed']==12 and not data['missing'];rows=data['rows'];labels=['/'.join(r['scene_id'].split('_')[-3:]) for r in rows];y=np.arange(12)
plt.rcParams.update({'font.family':'serif','font.serif':['Times New Roman','DejaVu Serif'],'font.size':9,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42,'ps.fonttype':42,'savefig.dpi':300})
fig,axes=plt.subplots(1,2,figsize=(6.75,4.5),sharey=True,layout='constrained')
for ax,key,factor,label in [(axes[0],'SO3_RMSE_deg',1,'Attitude SO(3) RMSE (deg; log scale)'),(axes[1],'position_Q_m',1000,'Position RMSE (mm)')]:
 old=np.array([r['C5_RBF']['metrics']['all'][key] for r in rows])*factor;new=np.array([r['CM18_A1']['metrics']['all'][key] for r in rows])*factor
 for yy,a,b in zip(y,old,new):ax.plot([a,b],[yy,yy],color='#B8BDC2',lw=1,zorder=1)
 ax.scatter(old,y,color='#475569',s=22,marker='o',label='C5 + attitude RBF',zorder=3);ax.scatter(new,y,color='#E76F51',s=26,marker='D',label='C5 + CM18-A1',zorder=4);ax.set_xlabel(label);ax.grid(axis='x',alpha=.2);ax.set_ylim(11.6,-.8)
 if key=='SO3_RMSE_deg':ax.set_xscale('log');ax.set_xlim(.0015,3.5)
 else:ax.set_xlim(0,20)
axes[0].set_yticks(y,labels);axes[1].tick_params(axis='y',left=False);fig.legend(*axes[0].get_legend_handles_labels(),loc='outside lower center',ncol=2,frameon=False,fontsize=8);fig.suptitle('Fixed 12-scene development screening: paired results',fontsize=10)
for ext in ['pdf','png']:
 p=D/f'fig_cm18_a1_screen12_paired_v2.{ext}';assert not p.exists();fig.savefig(p)
meta={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'scenes':12,'scope':'Development screening only; no independent-test or cross-seed claim','metric_alignment':'0<=t<20 transition-left rows; actual filtered attitude reference; all scenes retained','exports':['fig_cm18_a1_screen12_paired_v2.pdf','fig_cm18_a1_screen12_paired_v2.png']};(D/'fig_cm18_a1_screen12_paired_v2_metadata.json').write_text(json.dumps(meta,indent=2));print('EXPORTED_PDF_PNG_300DPI')
