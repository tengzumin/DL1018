function write_events_h5_dl1018(E,path,metadata)
% Write one event table as column datasets without adding file-hash metadata.
if nargin<3||isempty(metadata),metadata=struct;end
assert(istable(E)&&height(E)>0&&ischar(path),'DL1018:EventsWriteInput', ...
    'Expected a nonempty event table and an output path.');
assert(~isfile(path),'DL1018:EventsOverwrite','Refusing to overwrite an existing event file.');
folder=fileparts(path);if ~isfolder(folder),mkdir(folder);end
names=E.Properties.VariableNames;
for i=1:numel(names)
    value=E.(names{i});dataset=['/' names{i}];
    if isstring(value)||iscategorical(value)||iscellstr(value)
        value=string(value(:));width=max(1,max(strlength(value)));
        bytes=zeros(height(E),width,'uint8');
        for k=1:height(E),s=char(value(k));bytes(k,1:numel(s))=uint8(s);end
        h5create(path,dataset,fliplr(size(bytes)),'Datatype','uint8');h5write(path,dataset,bytes.');
    elseif islogical(value)
        value=uint8(value(:));h5create(path,dataset,[numel(value)],'Datatype','uint8');h5write(path,dataset,value);
    elseif isnumeric(value)
        value=value(:);h5create(path,dataset,[numel(value)],'Datatype',class(value));h5write(path,dataset,value);
    else
        error('DL1018:EventsColumnType','Unsupported event column %s.',names{i});
    end
end
if all(ismember(compose("x14_%d",1:14),string(names)))
    X=table_matrix(E,'x14_',14);write_matrix(path,'/x',X);write_matrix(path,'/x14',X);
elseif all(ismember(compose("x29_%d",1:29),string(names)))
    X=table_matrix(E,'x29_',29);write_matrix(path,'/x',X);write_matrix(path,'/x29',X);
end
for base=["target_raw","target_clip","target_normalized","applied_compensation"]
    cols=compose(base+"_%d",1:3);
    if all(ismember(cols,string(names))),write_matrix(path,['/' char(base)],table_matrix(E,char(base+"_"),3));end
end
metadata.array_layout='event-major, one event per row';
metadata.phase_code_mapping='0=STATIC,1=PRE,2=EXTEND,3=HOLD,4=RETRACT,5=RECOVERY';
metadata.event_count=height(E);
fields=fieldnames(metadata);
for i=1:numel(fields)
    value=metadata.(fields{i});
    if isstring(value),value=char(value);end
    if ischar(value)||isnumeric(value)||islogical(value)
        h5writeatt(path,'/',fields{i},value);
    end
end
end

function X=table_matrix(E,prefix,width)
X=zeros(height(E),width);
for j=1:width,X(:,j)=double(E.(sprintf('%s%d',prefix,j)));end
end

function write_matrix(path,name,value)
h5create(path,name,fliplr(size(value)),'Datatype',class(value));h5write(path,name,value.');
end
