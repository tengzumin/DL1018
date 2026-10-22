function result=check_dl1018_corrected_reference(projectRoot)
% Zero-Plant numerical regression through the production GET path only.
if nargin<1||isempty(projectRoot)
    projectRoot=fileparts(fileparts(fileparts(mfilename('fullpath'))));
end
projectRoot=char(java.io.File(projectRoot).getCanonicalPath());
addpath(fullfile(projectRoot,'matlab','scenes'),fullfile(projectRoot,'matlab','runtime'));
specPath=fullfile(projectRoot,'configs','scene_specs.csv');
io=detectImportOptions(specPath,'VariableNamingRule','preserve');
io=setvartype(io,{'scene_id','split','task','class_id'},'string');
M=readtable(specPath,io);
M=M(ismember(M.split,["TRAIN","VAL","DEV"]),:);
splits=["TRAIN","VAL","DEV"];tasks=["HELIX","FIG8_3D","SQUARE"];
maxPositionError=0;maxVelocityError=0;maxAccelerationError=0;oldFig8Error=0;scenesChecked=0;
defaultRootScene=make_scenes_dl1018('GET',[],char(M.scene_id(1)));
assert(strcmp(defaultRootScene.metadata.reference_contract_id,'DL1018_SCENE_REF_FIG8_A2_V2'), ...
    'DL1018:ReferenceRegressionDefaultRoot','GET with an empty root did not resolve the project root.');
for split=splits
    for task=tasks
        rows=M(M.split==split&M.task==task,:);
        assert(~isempty(rows),'DL1018:ReferenceRegressionFixture','Missing %s/%s fixed scene.',split,task);
        sceneId=char(rows.scene_id(1));built=make_scenes_dl1018('GET',projectRoot,sceneId);
        assert(strcmp(built.metadata.reference_contract_id,'DL1018_SCENE_REF_FIG8_A2_V2')&& ...
            strcmp(built.scene.reference_contract_id,'DL1018_SCENE_REF_FIG8_A2_V2'), ...
            'DL1018:ReferenceRegressionIdentity','GET returned a wrong reference identity.');
        assert(string(built.spec.split)==split&&string(built.spec.task)==task, ...
            'DL1018:ReferenceRegressionSplit','GET selected a scene outside the requested split/task.');
        scene=built.scene;ref=scene.reference;t=scene.time(:);h=t(2)-t(1);
        [expectedP,expectedV]=expected_position_velocity(task,t);
        positionError=max(abs(ref.position(:)-expectedP(:)));
        velocityError=max(abs(ref.velocity(:)-expectedV(:)));
        assert(positionError<1e-12&&velocityError<1e-12, ...
            'DL1018:ReferenceRegressionPositionVelocity','Position/velocity changed for %s.',sceneId);
        ix=(3:numel(t)-2).';
        if task=="SQUARE"
            nearCorner=abs(t(ix)-5*round(t(ix)/5))<.003;
            ix=ix(~nearCorner);
        end
        numericA=(ref.velocity(ix-2,:)-8*ref.velocity(ix-1,:)+ ...
            8*ref.velocity(ix+1,:)-ref.velocity(ix+2,:))/(12*h);
        accelerationError=max(abs(numericA-ref.acceleration(ix,:)),[],'all');
        assert(accelerationError<1e-6,'DL1018:ReferenceRegressionAcceleration', ...
            'Five-point dV/dt disagrees with acceleration for %s (%.9g).',sceneId,accelerationError);
        if task=="FIG8_3D"
            oldA=old_fig8_acceleration(t);
            oldFig8Error=max(oldFig8Error,max(abs(numericA-oldA(ix,:)),[],'all'));
        end
        maxPositionError=max(maxPositionError,positionError);
        maxVelocityError=max(maxVelocityError,velocityError);
        maxAccelerationError=max(maxAccelerationError,accelerationError);
        scenesChecked=scenesChecked+1;
    end
end
assert(oldFig8Error>.1,'DL1018:ReferenceRegressionSensitivity', ...
    'The numerical check no longer distinguishes the old FIG8 half-acceleration terms.');
result=struct('reference_contract_id','DL1018_SCENE_REF_FIG8_A2_V2', ...
    'default_root_get_passed',true,'scenes_checked',scenesChecked,'max_position_error',maxPositionError, ...
    'max_velocity_error',maxVelocityError,'max_five_point_acceleration_error',maxAccelerationError, ...
    'old_fig8_acceleration_error',oldFig8Error,'plant_calls',0,'optimizer_steps',0,'test_accesses',0);
fprintf('DL1018 reference regression: %d TRAIN/VAL/DEV scenes, max |p| %.3g, max |v| %.3g, max 5-point |dv/dt-a| %.3g, old FIG8 error %.3g; Plant=0, optimizer=0, TEST=0.\n', ...
    scenesChecked,maxPositionError,maxVelocityError,maxAccelerationError,oldFig8Error);
end

function [p,v]=expected_position_velocity(task,t)
s=min(max(t/20,0),1);u=10*s.^3-15*s.^4+6*s.^5;
ud=(30*s.^2-60*s.^3+30*s.^4)/20;
switch task
    case "HELIX"
        th=3*pi*u;p=[1.2*(cos(th)-1),1.2*sin(th),2*u];
        pu=[-3.6*pi*sin(th),3.6*pi*cos(th),2+zeros(size(t))];v=pu.*ud;
    case "FIG8_3D"
        th=2*pi*u;p=[1.5*sin(th),sin(2*th),.4*u+.35*(1-cos(2*th))];
        pu=[3*pi*cos(th),4*pi*cos(2*th),.4+1.4*pi*sin(2*th)];v=pu.*ud;
    case "SQUARE"
        p=zeros(numel(t),3);v=p;points=[0 0 0;2 0 0;2 2 0;0 2 0;0 0 0];
        for k=1:numel(t)
            segment=min(floor(t(k)/5),3);q=min(max((t(k)-5*segment)/5,0),1);
            h=10*q^3-15*q^4+6*q^5;hd=30*q^2-60*q^3+30*q^4;
            dp=points(segment+2,:)-points(segment+1,:);
            p(k,:)=points(segment+1,:)+dp*h;v(k,:)=dp*hd/5;
        end
end
end

function a=old_fig8_acceleration(t)
s=min(max(t/20,0),1);u=10*s.^3-15*s.^4+6*s.^5;
ud=(30*s.^2-60*s.^3+30*s.^4)/20;udd=(60*s-180*s.^2+120*s.^3)/400;
th=2*pi*u;pu=[3*pi*cos(th),4*pi*cos(2*th),.4+1.4*pi*sin(2*th)];
puu=[-6*pi^2*sin(th),-8*pi^2*sin(2*th),2.8*pi^2*cos(2*th)];
a=puu.*(ud.^2)+pu.*udd;
end
