function [C, geometry] = allocation_matrix(lengths, P)
    % FUNCTION:
    %   构造旋翼平方转速到总推力和机体系力矩的控制分配矩阵。
    % PURPOSE:
    %   按旋翼相对当前总 CoG 的力臂计算滚转/俯仰力矩，并按旋向符号计算偏航反扭矩。
    % INPUT: lengths 为四个旋翼中心半径（m）；P 提供 CoG、kf、km 及臂安装角。
    % OUTPUT: C 满足 wrench=C*omega.^2，wrench 顺序为 [总推力; Mx; My; Mz]（N、N*m）；可选 geometry 返回各旋翼位置。
    %ALLOCATION_MATRIX CoG-aware rotor-to-wrench map for one parameter object.

    lengths = double(lengths(:));
    assert(numel(lengths) == 4 && all(isfinite(lengths)) && all(lengths > 0), ...
        'TCNNEW:ArmLength', 'Allocation requires four finite positive arm lengths.');
    [directions, angles] = arm_directions(P);
    rotorPositions = directions .* lengths.';
    relative = rotorPositions - P.cog;
    C = zeros(4);
    C(1,:) = P.kf;
    C(2,:) = P.kf * relative(2,:);
    C(3,:) = -P.kf * relative(1,:);
    C(4,:) = P.km * [1,-1,1,-1];
    if nargout > 1
        geometry = struct('angles',angles,'directions',directions, ...
            'rotor_positions',rotorPositions,'relative_rotor_positions',relative);
    end
end
