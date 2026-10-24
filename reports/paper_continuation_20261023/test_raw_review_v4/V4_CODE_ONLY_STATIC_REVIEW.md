# 最终 TEST raw reader v4：CODEONLY 静态适配

当前只生成源码与完整 diff，未执行 reviewer CLI，未打开任何 TEST raw/成绩。正式 TEST 仍由原 session68299 顺序执行，本 reader 不启动 MATLAB、Plant 或训练。根实际审核后，且 B48 加五方法均取得自然 OS0，才可运行最终 CLI。

原 v3 reader 原样保留，SHA256 `05dc4f7e36307fac91df25e0cba4ae5def3f7156a8afb29e85dd3b436527615f`。新 reader SHA256 `5d394bf133d9700dd0852aa43d1da780195557efe4e3a8e3aeece67fa2137fe5`；完整 diff `V4_CODE_ONLY_ADAPTATION_DIFF.patch`，SHA256 `890f0cb97176563888f6f3209c3b6012908924c88570af2bc33878654dae9115`。

变更仅涉及输入身份、路径、失败披露和 spec 序列化范围：

- 绑定最终 v9 的 entry/launcher/contract/manifest、v2 taskbook/code-only release 及正式 TEST release SHA。B48 继续 v3，五方法读取 v9。schema 仍为已发布的 V4 协议。
- D/K manifest 的历史参考 lineage 只接受已确认的两组 old→corrected run_start SHA，分别桥接 superseded legacy 与 r002/r001；模型、source 集合（原 PCF helper 例外）及部署 collector 映射不变。
- 冻结 cfgpack 仍为原 `389fdfab...` 字节。runIdentity/meta 的 method_cfg_opts_snapshot_sha256 仍校验整个 cfgpack，绝不要求其内部旧模板 metadata 改写为 corrected 参考 SHA。
- 保留 v3 失败、v4 失败与路径诊断，并增加 v5/v6 的 prior prepare、v5 DEV2 零 Plant 失败、v6 一次 VAL Plant 失败、v7/v8 prepare 零 Plant 失败。receipt、日志、历史源文件和 v6 保留 raw 均有 SHA 门禁；均排除在 288 条 TEST 成功行之外，纳入真实进程时间顺序。
- 最终 DEV2 result/OS 的四个 engineering_DSSM/KAN SHA 字段使用实际 release 大小写；新增检查 DEV2 的 source snapshot/raw 精确对应 corrected engineering specs。
- MATLAB opaque spec table 仍严格比较现有解码器返回的 storage header，同时明确声明表内容未独立语义解码；新增属性类型门禁，禁止把整数 header 相等称作完整表语义相等。物理 scene/cfg/opts、事件及权重检查维持原冻结实现。

静态验证：AST/compile 通过，未 import/运行新 reader 模块。仅在隔离 AST 函数中用实际两条 DEV2 JSON 验证 PCF which/cell 形状，通过；四个 engineering SHA 字段已对实际 release 逐项核实。评分、事件、native readiness 和最终数字闭合检查大段在规范版本标识后与原 v3 源码逐字相同，块 SHA256 `1c17a6ad8e583d27cc16acf2ccbac0db44a6daf590c137af02f8b77475c88906`。READY_CUTOFF_S、score_one、event_audit、audit_events、W0、所有门槛和 tolerance 未改，冻结 v1 reader SHA 仍 `31229d1b9d137ec2847b25b7a32c3d0183e517fac963dc2ed01de74bcde11d45`。

尚未进行最终真实 raw CLI 验收；这需要全部六方法自然 OS0 和根单独审核授权。
