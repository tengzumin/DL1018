function a=trim_head_audit_v39(a,n)
% Trim row-vector and matrix audit fields using the original preallocated length.
maxN=numel(a.time);n=min(n,maxN);f=fieldnames(a);
for i=1:numel(f)
    v=a.(f{i});
    if ndims(v)==3
        a.(f{i})=v(:,:,1:n);
    elseif size(v,2)==maxN
        a.(f{i})=v(:,1:n);
    else
        a.(f{i})=v(1:n,:);
    end
end
end
