# GRU_STREAM cosine deployment snapshot review

**结论：** 未发现新的控制分支或场景绑定阻断。只读文件/SHA审查；未运行 Plant、训练或 TEST。`ROOT_GRU_STREAM_COSINE_TASKBOOK_v1.md` 将全72拟合/梯度结果限定为离线证据，不宣称闭环改善；首场须单独审核后才扩其余五场。

- `SOURCE_DIFF_v1.json` 声明与直接 parent `gru_stream_dev_v1` 的58个 `.m` 零差异；本次逐项 SHA 复核为58/58锁匹配、58/58 parent 一致。source lock SHA `fd67ac363ab5faef2e4893bf6b6dfc6f611327d36625161040f002c4b87ab86f`，source diff SHA `eab1f5dad07d5802c21c63181eb9a8fa1eba41c8d0a09aa71c845d91ee4448b6`。
- Candidate/manifest/release/Python parity/MATLAB parity均指向 `gru_stream_cosine_c5_teacher_v1/runs/GRU32_STREAM72_COSINE_S2026102001/gru_stream_c5_teacher_weights_v1.mat`；实际模型SHA复核为 `b2c462f77a6bb97b8c6bb2b471daef0633d4f9664a7d623b894461a4fa21b567`。outer driver只接受 study/candidate匹配的release和manifest六个VAL场景，并由release model path加载及核SHA；每场先核场景payload/配对B、C5等源raw身份，再建marker。
- raw auditor固定读取本study `RELEASE.json`，NO_PLANT检查引用正确为 `audits/NO_PLANT_CHECK_v1.json`；writer新加的release快照绑定已核实：当前 `releaseSha` 分别与 `raw.runIdentity.release_sha256`、`log.gru_stream_release_sha256`、`runStatus.release_sha256` 比较。current auditor SHA `6e86f0be118d9c4560e041f766cfdf21519c82c6610f1a66ad44ade1a179b084` 与当前 `RELEASE.json` 的 `raw_audit_script_sha256` 一致。
- current `RELEASE.json` SHA `a1439eac99258513f9b8c0461c3285cbfb559cbed0e2319c6116bba46dbb6209` 仍是 `PREPARED_ROOT_REVIEW_REQUIRED`，授权和已调用 Plant 均为0；首场前仍保持封闭，待root单独签发。

未发现其他实质阻断。
