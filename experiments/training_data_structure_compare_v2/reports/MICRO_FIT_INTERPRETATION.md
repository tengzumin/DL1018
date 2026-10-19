# 微型可拟合性探针

固定池：HELIX / FIG8_3D / SQUARE，C00，W04/W08，B/POS_OFF，共12条 TRAIN episode、4,728个stride-5终点。随机种子2026101909，两模型使用相同预生成窗口顺序、相同 TRAIN-only Initial normalizer、Adam 1e-3、weight decay 1e-5、batch256、6,000步。没有读取VAL/DEV，模型均标为DIAGNOSTIC_ONLY，不进入Plant。

KAN参数量4,163；MLP参数量22,659。6000步训练物理RMSE：KAN 0.228615 m/s²，MLP 0.145438 m/s²。结论：**宽MLP明显更好**。参数漂移、梯度范数、逐轴偏置、标签RMS及预测标准差/塌缩标记见`MICRO_FIT_CHECK.csv`。

本探针只回答已见小池上的优化与拟合能力。它不是外推成绩、等参数容量对照或闭环证据，也不用于修改标签/删除样本。
