# DEV72 冻结 W0 目标平移能量分解：准备说明

## 既有证据与覆盖边界

目标坐标关系本身已知，不应被写成新发现。`reports/train_pcf_contract_parent_review_20261022/COORDINATE_INTERPRETATION_ZH.md` 和 `FINAL_REVIEW_ZH.md` 已明确在相同状态、固定 W0 下比较旧目标 Y 与匹配目标 Y+M r_f。TRAIN1536/训练 VAL96（不是 C5 的 VAL48）的证据来自 Teacher B/POS_OFF 轨迹；已有汇总包括逐轴、风组和 `early_lt_5s`/`late_ge_5s`，并显示 HF 两目标的先验均优于零预测但 Y 的 W0 拟合优于 Y+M r_f，无风先验整体较弱。报告已明确目标变换并未单独消除先验失配，Teacher 影子轨迹也不能代表候选 PCF-on 闭环。

`reports/delayed_prediction_c3_dev72_parent_20261023/PARENT_T2_HF_FIXED_INPUT_FIT_REVIEW.json` 只覆盖 C3 的 9 个 T2 高频场景 Z 轴，在同一 C3 轨迹上比较 Wk/W0 拟合；它没有比较 y0/yM，也不覆盖 C5 M110 的 X/Y 或完整 DEV72。

相关的 `realization_mechanism_review` 说明了延迟标签 `dot v-a_f=Y+r_f` 和 PCF 路径；`sampled_error_accounting` 分解 C3 闭环位置误差的 eta、残差误差和采样余项。这两项都不是 C5 的固定 W0 目标误差分解。

因此公式、目标对照和启动窗口并非新内容。唯一可能新增的信息来自**不同的运行轨迹域**：冻结 C5 M110 候选的 PCF-on 开发侧72场记录（24 DEV、48 VAL；不含 TEST）。脚本检查同一条 C5 记录中的 `phi_prev`，对比冻结 W0 面对 Y 与 Y+M r_f 的误差变化，并把现有分组/时段分解写成逐轴显式交叉项。它可以判断旧 Teacher B/POS_OFF 结论在 C5 实际候选运行记录上是否复现或偏离，但仍是描述性先验失配检查。

若目的是证明标签平移造成闭环性能差异、证明修改标签可修好控制器，或提出新坐标恒等式，这项分析不值得运行，也无法支持那些结论。若需要回答“冻结 C5 路径上的 W0 目标误差由平移项贡献多少”，这个不同数据域的窄对照有价值；脚本仍须经根审核后才能读取批量 raw。

## 准备的计算

脚本只读 C5 DEV72 父审 JSON 所固定的 72 条 C5 raw。它调用已 pin 的 MATLAB v7.3 decoder 归一化所选日志叶，并沿用 C5 event audit 已校核的事件索引、冻结 W0 SHA 和标签对齐字段。对有效事件相邻对 `j -> k`，用与审计源相同的区间累积积分差取样：

- `y0 = (v[k]-v[j])/(0.001*(k-j)) - mean(a_req[j:k])`
- `c = mean([1,1,0] * r_f[j:k])`
- `yM = y0+c`，并核对日志中 endpoint `k` 的 delayed target
- `e_phys = W0^T phi_prev - y0`，`e_coord = W0^T phi_prev - yM`
- 分轴及三轴总和计算 `E_phys`、`E_coord`、`sum ||c||^2` 和 `-2<e_phys,c>`，逐区间及汇总检查恒等式

输出预设覆盖 ALL72、HF W09–W14、W15、T1/T2/T3 和 0–5s、5–20s；并保留每场/每分组、每阶段、逐轴平方和与每区间均值。早晚分段按完成区间端点定义，0–5s 含结束时刻 5s 的区间，5–20s 从起点 5s 的区间开始。

该计算只测量冻结 trained W0 在记录的 `phi_prev` 上面对两种相邻区间标签时的目标误差差异；不使用自适应后的权重，不代表闭环反事实、位置误差因果、稳定性或新颖性。脚本尚未执行，也没有读取 DEV raw；须待根审核后再决定是否运行。

## 输入字段与身份

事件和目标字段（已出现在冻结 C5 审计源中）：`stage1_position_event_inference_valid`、`stage1_position_event_phi_33`、`stage1_position_search_initial_weight`、`state`、`stage1_position_pcf_a_req_mps2`、`stage1_position_pcf_r_f_mps2`、`stage1_position_coordinate_mask`、`stage1_position_delayed_prediction_target_mps2`、`stage1_position_delayed_prediction_prev_index_zero_based`。

输入身份见 `INPUT_IDENTITY_v1.json`。它固定 C5 开发侧 DEV72（24 DEV、48 VAL）审核清单、run contract 的 DSSM14 seed 2026102001/step 60000/W0 SHA `88f8c4f2…a0c2cf53`、M110 `[1,1,0]`、C5 event audit 和 pinned decoder SHA；运行脚本时还逐 raw 核对父审登记的 SHA。当前准备阶段只读了这些清单/源文件，不打开 raw；该72场结果是已冻结开发集的描述统计，不是新的独立验证。

## 根审后复现命令

```powershell
python -B reports/paper_continuation_20261023/dev_prior_target_translation_v1/decompose_prior_target_translation_dev72.py
```

当前没有运行上述命令，未读取 raw、未运行 scorer、Plant、训练或优化。若获根审后执行，输出文件已设为禁止覆盖。

