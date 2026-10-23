# C5 DEV72 独立工程预审（草稿快照）

本次只读核验当前 C5 DEV72 builder、prepare、runner、PowerShell 启动器及其小型 JSON 元数据；没有运行 builder/noPlant/MATLAB/Plant，也没有读取 raw 或 MAT 内容。当前源码仍可能继续编辑，本记录不构成最终冻结审核。

## 发现

`experiments/position_axis_coordinate_c5_dev72_20261023/freeze_c5_dev72_inputs_v1.py:382` 生成的 `C5_DEV72_PARENT_RELEASE_CONTRACT_v1.json` 将 `exact_scene_order_source.field` 写为 `scene_ids_new_60`。冻结任务书指定的来源是 C3 lock 的 `scene_ids_all_72`，再按 reuse12 过滤且保持顺序。builder 第101–102行对 60/12 列表的实际构造与原72顺序筛选一致，故当前发现是 release 合同中的来源声明偏差，不是已观察到的场景运行顺序偏差。冻结前应更正来源字段并重建其下游绑定。

## 已核验

- 当前 builder/prepare/runner/两条 PS1 的 SHA 分别为 `1fe4aa9927d0443102bb89c0d9a75caea53eb7dab95bbfb737d695316bd47d11`、`7cedf7237a7375c398d21c9903e6cb02ab866041b704cc43c879366881688366`、`22b12c0812c2c39f053e9653728f0f26b508ffdb8bb9936f211fb8bd5b497015`、`367833156b4ec77c68143bf83134a5aae8933f323bd362c22ccb51f537d1cb28`、`8d1b74397244f8acbb0c46027f3b0f54bae4e55fb677c88b1894189855b88307`。已生成的 lock、run contract、release contract、source binding SHA 分别为 `d52fe068924d35115c1fcc76be0c956fb23f18d85ed72ad115ce6afd64481458`、`d61681ca5f25975e482127b3c52680b17ce6cbe9d409be559157aea0a71a7677`、`bc40688993be57adaad2433a62247f323f0d42ababd0c9a2d9facb26f51bc4c4`、`9c7b1f4236dddcea03676a6029ff7951166b466b288623e8eaab12907e4aa4f2`。锁中的入口/来源引用与当前脚本哈希一致。
- JSON 元数据字段映射通过：72 个场景保持 C3 顺序，其中 60 个新场、12 个 C5 复用；B72 比较清单顺序与该72场一致；C3/B72/C5 结果状态引用共 156 份，状态、scene ID、raw path 与登记 SHA 字段匹配。锁、contract、binding 的 scene-id 向量一致；可读 JSON 上游引用的路径及 SHA 匹配。`.mat` 只核对锁定路径存在性/引用映射，未读取其内容；raw 内容及其实际 SHA 未在本次读取。
- C3 物理场景源与 B72 评分来源字段在 builder、锁和 runner 的引用分开；C5 复用状态限定在12场。prepare/runner 消费的主要 lock/contract/binding 字段在已生成小型 JSON 中存在，未发现其它缺字段或路径映射错误。

最终 release 前须以作者停止编辑后的文件重新计算并审核 SHA；本快照不替代无 Plant prepare 的实际结果与主审放行。
