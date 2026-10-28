function root=activate_paired_runner()
% Resolve every copied MATLAB source from this tree before a later audit/run.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
restoredefaultpath;
rehash toolboxcache;
folders={'core','models','runtime','scenes'};
for i=1:numel(folders)
    addpath(fullfile(root,'matlab',folders{i}));
end
for i=1:numel(folders)
    sourceDir=fullfile(root,'matlab',folders{i});
    entries=dir(fullfile(sourceDir,'*.m'));
    for entry=entries.'
        [~,name]=fileparts(entry.name);
        assert(strcmpi(which(name),fullfile(sourceDir,entry.name)), ...
            'PAIRED:SourcePath','Source resolved outside paired_runner: %s.',name);
    end
end
end
