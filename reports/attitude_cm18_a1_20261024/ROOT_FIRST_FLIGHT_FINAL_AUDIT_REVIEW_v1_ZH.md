# 首航逐事件最终审核

实际 MATLAB R2025b session16615终止OS0，A1_FIRST_FLIGHT_LOG_AUDIT_v1.json状态PASS，原始raw SHA cb70eec663da6248d6291fb4b64bdf943cdf284a1d608313edb166c616d771f9。

ROOT完整阅读审计逻辑并运行实际raw。1,999事件：X18、过去命令积分、过去10个已完成transition的请求力矩均值、固定控制器BS重建、独立网络forward、限幅、beta、保持加速度/力矩、J0与nominal-minus-comp闭合全部max delta=0。姿态RBF运行、输出、更新关闭；三种安全持续越界时长均0；电机饱和、广义限幅、姿态倾角限幅、CM18补偿限幅均0。Python/SciPy独立评分与MATLAB评分一致。

审计脚本attempt1因formalRbfBaseline按设计删除的冗余诊断字段而失败；ROOT删除该字段的冗余检查，保留实际应用补偿与CM18held闭合。未修改已执行控制器、模型、runner、场景或raw。原失败控制台与OS记录保留。

决定：固定单场工程检查通过，支持进入原已冻结SCREEN12剩11场；当前仅允许准备及审核执行脚本，最终放行文件须绑定修复后的源码和11个输入身份。此结论不等于论文性能达标。
