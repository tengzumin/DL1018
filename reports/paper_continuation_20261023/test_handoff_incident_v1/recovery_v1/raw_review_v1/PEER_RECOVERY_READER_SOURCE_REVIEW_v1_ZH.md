# Recovery288 Reader 源码独立复核

**结论：未发现阻断性源码缺陷。** 当前 reader audit_test48_raw_recovery288_v1.py SHA-256 为 a709201623d9e9f0e4b312946a1db35021bd5aa379c9f7ca04af3147e4be79d0；对照基线 v5 SHA-256 1c7380abd2b1f29e0f7045017abaeef87f54d751ad74a710bfbdbdac504730ff，以及冻结 tail writer run_dssm_tail16_v1.m SHA-256 d8e2c47f1310eed71922aa580f9881ca1d508110c3e45fbacf6461a2d66f11fc。复核范围限于源码及既有 JSON 元数据；没有读取 TEST raw，没有运行 reader、评分或 MATLAB。

## 核对结果

- **Tail 身份字段与冻结 writer 相符。** writer 的 runIdentity 保存 model_identity（含 W0_sha256），没有 initial_weight_identity 字段。reader 在 verify_recovery_tail_run_identity 中按 writer 的 schema、方法/场景、canonical 33–48 与 local 1–16 索引、entry/launcher/scope/release/source/config SHA、run_start 和 Plant marker SHA、时间、路径、执行标志、模型和全局绑定逐项核对；明确用冻结 model_identity 比对模型身份，并由后续数值初始权重审计验证 raw 中的 W0。这里没有要求 writer 不会生成的字段，也没有补造身份字段。
- **DSSM 三段拼接和 scene32 例外保持透明。** reader 要求 first31 父级文件审计、从 scene32 父报告取得 raw/run_start SHA，并核对 scene32 仍缺少 runIdentity、原 status 仍是 RUNNING_PREPLANT。它只在读者侧标记例外，没有向 raw 或 history 写回身份。tail batch/body 的 16 条记录相等，canonical/local 索引与冻结 48 场顺序逐项吻合；当前既有 JSON 显示 tail 为 16 条，indices 33–48 / 1–16。
- **历史 OS 未被重新归类。** 源码多处保留 original_DSSM_natural_os_exit=UNKNOWN 和 UNMET_DO_NOT_RECLASSIFY。receipt 时间线只包含有凭证的 B48 和五个 Recovery208 新进程；原 DSSM 旧进程被明确排除在时间线之外，说明原因是没有权威自然退出凭证。Tail 的 OS0 收据只证明 tail16 新进程。既有 tail receipt 元数据显示自然 wait、OS 0、16 calls，与 tail batch/body 状态一致。
- **receipt 检查在 TEST raw 和评分之前。** run_review 先核验 recovery release/scope/source、B48 receipt、全部五个 Recovery208 process receipts、历史过程顺序及时间，再进入方法记录与 raw 的读取/评分环节。静态调用顺序符合“先 receipt，后 raw”；DSSM 旧进程的 UNKNOWN 不会被其他 receipts 填补。
- **评分、事件、物理身份及有限性检查保持一致。** 当前 reader 将 score_one、C5 与 ablation event auditors、native/actuator 结果和 v5 相同地接入冻结 v1 reviewer（锁定 SHA 31229d1b9d137ec2847b25b7a32c3d0183e517fac963dc2ed01de74bcde11d45）。对 v5 与当前源码按相同锚点、LF 行连接后比较，以下片段逐字相等：评分行/事件审计路径 SHA-256 5f01b2760267bac2e2670a623d50397e2c210b053d54f49f5815715b13476b63；逐场外部物理身份与事件计数检查 SHA-256 19fded02ce9391eccd54522e7bc974a82bae37500389d5dc204756d4c34631f7；行状态与 actuator completeness 检查 SHA-256 9a1fcb4f3f94559378772349afefa6a435185d52ef7ec3e543a6149ffcda3e3c。Recovery288 自身再要求 48 场 × 6 方法的 288 个唯一 (scene, method) 对、方法顺序、逐场六方法 external identity 一致、144 个 C5 事件审计、96 个 corrected-method 初始权重数值审计及总调用数 288。变化集中于来源适配、receipt 与 legacy gate 披露，没有放宽评分或物理检查。
- **路径和输出边界正确。** 新 reader 位于 raw_review_v1 下，Path(__file__).resolve().parents[5] 回到 DL1018 仓库根；输出路径解析后必须直接位于自身目录，且拒绝覆盖已有文件。

## 需保留的说明

PARENT_READER_INTERIM_REVIEW_v1.json 的状态明确是 interim，所记录 reader SHA e9664c87665c38c6d92039d485144bf4751c75b7cfa7463a47d9a7dd65933f5b 早于当前冻结 SHA；不要把该 interim 文件当作当前 reader 的 source approval。任务书的 aggregate protected-block SHA 与 interim JSON 中的 digest 使用不同摘取口径；本复核不声称二者相等，而以文中列出的相同锚点逐片段比较作为源码证据。

静态复核未运行任何测试或评分入口；没有打开 TEST raw、没有启动 MATLAB/Plant。
