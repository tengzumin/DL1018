function [inertia,cog,inertiaDot,cogRate,details] = arm_mass_properties(lengths,plant,rates)
    % FUNCTION:
    %   通过统一的 distributed_v1 几何模型计算变臂飞行器质量属性。
    % PURPOSE:
    %   将当前臂长及其变化率转交给 distributed_mass_properties，保证 Plant 和风载复用同一几何定义。
    % INPUT: lengths 为四个旋翼中心半径（m）；plant 为 Plant 质量/几何参数；rates 为对应臂长变化率（m/s）。
    % OUTPUT: inertia（kg*m^2）、CoG（m）、inertiaDot（kg*m^2/s）、cogRate（m/s）及分量几何 details。
    % NOTE: 当前实现要求 mass_model 为 distributed_v1；这些数值是仿真模型属性。
    %ARM_MASS_PROPERTIES The single TCN0901 distributed_v1 mass-property path.
    if nargin < 3 || isempty(rates),rates = zeros(4,1);
    end
    assert(isstruct(plant) && isfield(plant,'mass_model') && strcmpi(char(string(plant.mass_model)),'distributed_v1'), ...
        'TCN0901:MassModel','TCN0901 requires plant.mass_model=distributed_v1.');
    [inertia,cog,inertiaDot,cogRate,details] = distributed_mass_properties(lengths,plant,rates);
end
