root=fileparts(mfilename('fullpath'));
addpath(root);
candidate=fullfile(root,'delayed_prediction_step_candidate.m');
issues=checkcode(candidate,'-id');
W=reshape(sin(1:99)*0.2,33,3);
phi=zeros(33,1); phi(1)=1;
oldPhi=zeros(33,1); oldPhi(2)=1;
s=[1;-2;3]; y=[0.3;-0.2;0.1];
first=delayed_prediction_step_candidate(zeros(33,3),phi,[0;0;0],320,0.32,[],[],[],[]);
second=delayed_prediction_step_candidate(W,phi,s,330,0.33,oldPhi,y,320,0.32);
result=struct('status','MATLAB_NO_PLANT_KERNEL_EXECUTED','checkcode_count',numel(issues), ...
    'checkcode_ids',{{issues.id}},'first',first,'second',second);
fid=fopen(fullfile(root,'matlab_kernel_result.json'),'w');
fwrite(fid,jsonencode(result),'char');
fclose(fid);
disp(jsonencode(struct('status',result.status,'checkcode_count',result.checkcode_count)));
