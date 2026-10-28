function hash=paired_sha256_double(value)
% SHA-256 of column-major IEEE-754 double bytes on the frozen MATLAB host.
assert(isa(value,'double')&&isreal(value)&&all(isfinite(value(:))), ...
    'PAIRED:HashInput','Expected a finite real double array.');
md=java.security.MessageDigest.getInstance('SHA-256');
md.update(typecast(value(:),'uint8'));
hash=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end
