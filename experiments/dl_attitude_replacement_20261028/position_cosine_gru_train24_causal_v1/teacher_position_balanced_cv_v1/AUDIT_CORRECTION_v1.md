# 审计注记：折分文字更正与 teacher 用途

原始预声明配置保持不变，SHA-256 仍为 `221669a3dfd6d8fde14a0b0975086826a11ac99e79e97a7a8b91ddba06572a49`；原 source lock 也未修改。

配置中的“每折 18 个训练场景”是文字误写。实际 train/holdout 数分别为 **18/6、16/8、20/4、18/6**，与四个固定 scene-group 折的逐场 ID 清单一致。代码通过 manifest 中每折的 `train_scene_ids` 建立索引，归一化和两项 loss RMS 均由对应训练索引计算；因此实际训练尺度遵循分折实现，没有用留出场景估计。

Teacher delta 仅作为训练折上的辅助监督目标。部署时不加载 teacher、不需要 teacher 输入，也不在推理或 `tau_score` 评分中调用 teacher。
