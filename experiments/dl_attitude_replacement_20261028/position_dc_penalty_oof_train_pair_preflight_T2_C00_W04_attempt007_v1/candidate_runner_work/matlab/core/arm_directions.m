function [directions, angles] = arm_directions(plant)
    % FUNCTION:
    %   根据四个机臂安装角生成机体系中的单位方向向量。
    % PURPOSE:
    %   为分布质量位置和旋翼控制分配提供一致的 X 形平面几何定义。
    % INPUT: plant 可提供 arm_angles（rad）；缺省时使用相对机体轴旋转 45 度的安装角。
    % OUTPUT: directions 为 3x4 机体系单位方向矩阵，angles 为对应角度行向量（rad）。
    %ARM_DIRECTIONS 生成 X 形布局的四个机臂方向。

    if nargin < 1 || ~isstruct(plant) || ~isfield(plant,'arm_angles')
        angles = pi / 4 + (0:3) * pi / 2;
    else
        angles = double(plant.arm_angles(:).');
    end
    assert(numel(angles) == 4 && all(isfinite(angles)), ...
        'TCNNEW:GeometryContract', 'arm_angles must contain four finite values.');
    directions = [cos(angles); sin(angles); zeros(1,4)];
end
