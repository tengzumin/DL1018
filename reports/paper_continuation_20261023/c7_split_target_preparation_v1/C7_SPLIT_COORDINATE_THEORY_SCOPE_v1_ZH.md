# C7双坐标的误差关系与继承范围

固定跟踪坐标Ms=diag(1,1,0)，预测目标坐标My=0。令d0=a_actual-a_req（离散日志用速度增量定义），rf=a_req-af，dY=d0+My rf，epsilonY=u-dY，sc=s-Ms eta。连续理想式为

    sc_dot=-e-K2 sc+epsilonY+(My-Ms)rf,
    e_dot=sc+Ms eta-K1 e,
    u-d0=epsilonY+My rf.

因此C7即使完美预测physical d0，也不能同时使sc方程的目标误差消失；额外项是−Ms rf。不能把Ms和My相等时的自适应交叉抵消原封不动当成新臂的闭环证明。输出beta渐入、clip、tracking面clip、100Hz保持、延迟标签、投影和泄漏仍需保留。

已接受的联合投影有限路径预测界(B)对任意实际因果完成区间标签成立，故其代数工具可继承；但须使用C7实际标签和实际tracking bias重新实例化，不能复用C5数值证书。实际输出到物理forcing的F分解应恢复My rf，不能误用Ms rf；C7 My000时最后一项为零，所有实际forcing由epsilonY及既有pre-ready/tail与采样余项承担。协调方程另有(My−Ms)rf，但直接物理(e,sigma)递推不得再加此项，否则重复记账。

理论检查只支持明确的机制消融，不证明Q改善、稳定性、无风必胜或方法原创性。此文未引入新的控制器，也没有新增Plant调用。
