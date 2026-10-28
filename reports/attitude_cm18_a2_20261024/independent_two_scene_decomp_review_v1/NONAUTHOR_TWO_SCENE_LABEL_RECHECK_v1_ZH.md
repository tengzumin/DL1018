# 两场旧 yaw 标签分解：独立数值复核（以v2为准）

复核只读取v2逐事件分量JSON，以及两个 pinned event cache 的 `target_raw(:,3)`、`phase_code`、`plant_index` 与身份字段。两场各1999事件，共3998事件；按事件行逐项对齐，并重新计算分量和、每相位均值/RMS、所有component pair的二阶交叉项和分量展开二阶矩。未读取 raw_run、TEST、checkpoint；没有模型推理、GPU、Plant或训练。

## 结果

| Scene | cache target与JSON逐事件最大差 | 分量和对cache最大差 | 二阶矩展开差 | 旧动作项RMS | 删除旧动作项后label RMS | 旧动作项MSE差 | 风项RMS | 删除风项后label RMS | 风项MSE差 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| DL1018_TRAIN_T1_C15_W14 | 0 | 4.44e-16 | 0 | 0.220015 | 0.394665 | 0.169304 | 0.366556 | 0.236960 | 0.268914 |
| DL1018_VAL_T2_C15_W09 | 0 | 2.22e-16 | 0 | 0.185037 | 0.287294 | 0.129822 | 0.266093 | 0.201689 | 0.171681 |

分相位（STATIC/PRE/EXTEND/HOLD/RETRACT/RECOVERY）的component signed mean、RMS、删除旧动作项/风项后的label RMS与二阶矩变化见 `TWO_SCENE_LABEL_PHASE_RECHECK_v1.csv`。每个component pair的 \(E[c_i c_j]\) 与其对总二阶矩展开的两倍交叉项见 `TWO_SCENE_LABEL_PAIRWISE_CROSS_v1.csv`。各项RMS不能相加成总RMS或“占比”；删除项的MSE变化满足 `MSE(y)-MSE(y-q)=E[q²]+2E[q(y-q)]`，这里只是记录内的代数敏感性，不是因果效应。

## v1/v2与flag边界

v1曾把 `/log/controller_clipped_generalized` 的非零数值当作clip flag；运行源码实际记录 `a.clipped_generalized`，即裁剪后wrench数值。该v1 flag结论已弃用。v2改用裁剪前后wrench差推断controller clipping，并与allocator布尔flag交叉核对。两场均有7996个逐轴检查项，inferred controller clip、allocator clip及两者不一致计数都为0；v2两场 `simple_formula_applicable=true`。全广义力矩 realized/requested 的最大差仍分别为0.06005/0.05680 N·m，但yaw角加速度差只有约1.42e-14/1.35e-14 rad/s²；由于yaw逆惯量行与xy解耦，该全向量差不破坏此yaw标量公式。

## 边界与身份

只支持这两个旧记录与对应缓存的标签闭合，不推广到其他场景，也不把分量统计解释为闭环因果。v1与v2的3998条event_records逐条完全一致；v2仅修正裁剪元数据。
- v1 result SHA256：`020db63be4d94527849fddc6d422f440efac04e68cca23a26ade5a9e00c65fd5`；v1 source SHA256：`9e088df70a03dc6d1729fb7854a08349704b19f5fae33375e43825c73b242083`
- v2 result SHA256：`77e25178d0f091be4913736bc33f58d9018efa00ae9ee239c29311177a9a1c00`；v2 source SHA256：`f94d352b4ab674554e71c86133e2597efb1c2761a694eab974dac4e7354848a4`
- TRAIN cache SHA256：`2d87ad8962a243d24c2cb1845e3031e62e723dfa8a8ee0435a01cd90c4368f81`
- VAL cache SHA256：`29fe6f08c5a1349797bc2ea83c51efc389aa99893e71b91767e2733ace813a49`
