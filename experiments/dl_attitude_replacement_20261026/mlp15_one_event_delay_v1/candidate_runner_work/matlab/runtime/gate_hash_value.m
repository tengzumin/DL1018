function hash=gate_hash_value(value)
% SHA-256 over MATLAB's byte serialization for exact local identity locking.
bytes=uint8(getByteStreamFromArray(value));
md=java.security.MessageDigest.getInstance('SHA-256');
md.update(bytes(:));
hash=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
end