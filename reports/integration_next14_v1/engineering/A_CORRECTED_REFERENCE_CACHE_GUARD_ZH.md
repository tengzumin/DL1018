# A：正确场景参考接入与缓存隔离

日期：2026-10-22。范围仅为活动 MATLAB 场景源、Gate/collector guard、测试和本说明。没有运行正式 BUILD、总入口、训练、Plant episode 或 TEST。

## 修复与缓存风险

活动 `make_scenes_dl1018.m` 的 FIG8 参数二阶导已由 `[-6π²sin(θ), -8π²sin(2θ), 2.8π²cos(2θ)]` 改为 `[-6π²sin(θ), -16π²sin(2θ), 5.6π²cos(2θ)]`。position 与 velocity 公式未改。GET metadata 和 G01 报告使用身份 `DL1018_SCENE_REF_FIG8_A2_V2`。

旧缓存确实可能绕过新公式。`collect_position_dev_dl1018` 会先 GET 新 scene，再按固定 run ID 命中历史 raw，并用 raw 中保存的 scene 覆盖新 scene；G02 collector 会在 GET 之前跳过已 accepted 的 run。Python runner 的 PASS 快速跳过也曾在检查来源身份前发生。因此，单改公式或只写 metadata 不足以防止旧结果被当成新参考数据。

本次小型 fail-closed 改动如下：

- MATLAB BUILD 在任何输出前检查 G01 身份；G01 缺失时，已有 `scene_specs.csv` / `dataset_plan.json`、G02–G13 报告、非空 attempt/episode 索引、raw/events 内容或模型文件都会令 BUILD 拒绝。不会改写或迁移现存文件。
- 新增 `assert_scene_reference_contract_dl1018`；G02、role、DEV、dual 四个 collector 均在缓存读取前调用。MATLAB 下游 `run_gate_dl1018` 也在进入 gate 前校验身份。
- Python runner 在 `ensure_layout` 和 PASS 跳过前校验；CLI `--stage` 与 `--through` 在可能执行 G00 或写状态前只读预检。`--status` 保持只读。
- 正确身份的 PASS G01 正例允许通过；错误/缺失身份、缺 G01 但有旧账本、已 accepted/raw 缓存路径均有 fixture 负例。

当前工作区已有旧 G01/场景配置，因而会被上述 guard 拒绝。`GET` 只用于下述数值回归，不构成旧数据迁移许可，也不授权 collector 读取旧缓存。工程说明中的“新根”必须是包含代码与合同配置的自包含 DL1018 项目副本，且不能继承旧科学产物；`init_dl1018` 仍由自身 `.m` 文件位置解析 project root 并要求传入 root 一致。因此，任意空目录不是可直接 BUILD 的输出根。本轮未复制工程，也未声称新生产 pipeline 已通过。

## 零 Plant 数值回归

实际 MATLAB R2025b 通过生产 `make_scenes_dl1018('GET', ...)` 路径检查 9 个固定场景：TRAIN/VAL/DEV × HELIX/FIG8_3D/SQUARE。每个 scene 的 split/task 与请求相符；position、velocity 与独立写出的原公式逐点误差均为 0。对 velocity 使用五点中心差分并与 acceleration 对比；SQUARE 转角附近跳过 ±0.003 秒，避免把不连续点当作光滑导数。

结果：max `|p error|=0`，max `|v error|=0`，max 五点 `|dv/dt − a|=1.3310e-11`；将错误的旧 FIG8 加速度代入同一数值导数，偏差为 `0.6476`，超过测试的 `0.1` 灵敏度门槛。Plant=0、optimizer=0、TEST=0。该回归同时锁定了 HELIX/SQUARE 与 FIG8 的 position/velocity；只有 FIG8 加速度二阶项被修正。

执行命令与最终结果：

```powershell
& 'C:\Program Files\MATLAB\R2025b\bin\matlab.exe' -batch "addpath('C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/matlab/tests'); r=check_dl1018_corrected_reference; disp(r);"
```

exit 0。MATLAB stdout 报告 `scenes_checked=9`、`max_position_error=0`、`max_velocity_error=0`、`max_five_point_acceleration_error=1.3310e-11`、`old_fig8_acceleration_error=0.6476`、`plant_calls=0`、`optimizer_steps=0`、`test_accesses=0`。

## 缓存 guard 测试

MATLAB fixture 正例验证正确身份可通过；负例验证“缺 G01 + 非空 ledger”在 BUILD 写入前被拒、旧 G01 在 BUILD 前被拒，以及四类 collector 和 G02 Gate 在 synthetic accepted episode/raw 缓存前被拒。测试还确认 fixture ledger/raw 文件仍存在。fixture 保留在 `reports/integration_next14_v1/engineering/fixtures/tp0a9cdd14_3b08_43c8_a7de_303703c896ae`。

```powershell
& 'C:\Program Files\MATLAB\R2025b\bin\matlab.exe' -batch "addpath('C:/Users/35326/Desktop/postgraduation/0/Mcode/drone_tcn/DL1018/matlab/tests'); r=check_dl1018_reference_cache_guard; disp(r);"
```

exit 0。结果为 `valid_reference_identity_allowed=1`、`old_pass_rejected=1`、`missing_g01_with_ledger_rejected=1`、`accepted_cache_collectors_rejected=1`、Plant=0、optimizer=0、TEST=0。

Python fixture 共 6 项，全部通过；涵盖正确身份正例、旧 PASS 不可快速跳过、下游 gate 前置身份检查、缺 G01/旧 ledger、两种孤立 scene config，以及 `--through` 在 G00 写状态前拒绝旧 G01。fixture 使用工程内持久目录 `reports/integration_next14_v1/engineering/fixtures/python_scene_reference_*`。

```powershell
python -m unittest discover -s tests -p test_dl1018_scene_reference.py -v
```

exit 0，`Ran 6 tests`，`OK`。`git diff --check` exit 0；Git 仅提示 Windows CRLF 转换提示。

测试准备中出现的两项临时问题均已修正后重跑：首次数值回归命令漏加 runtime 路径，首次 MATLAB cache fixture 的 JSON 换行拼接错误。最初一轮 Python fixture 使用标准库 `TemporaryDirectory`；自动清理只删除了该测试自己创建的系统临时目录，没有触及项目或历史文件。随后正式 Python 与 MATLAB fixtures 均改为在上述 engineering 子目录创建且保留。最终通过结果对应当前文件版本。批处理 stdout 未单独保存为 `.log`；以上命令和完整关键数值即为本工程记录。

## 模型、参考源与评测入口

隔离实验的最新 G5 父审核状态为 `PASS_G5_TRAIN_COMPLETE`，最新 G6 MATLAB parity 状态为 `PASS_G6_MATLAB_PARITY`。因此这里引用 final60k 与 parity 通过证据；早期任务书中尚未完成的段落不是当前状态。

以下模型与实验文件均保留原位，本次没有复制、移动或修改：

- 只读隔离正确参考生成器：`C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\REFERENCE_FIX_FULL72_20261021_022342_313\sources\reference_fixed\make_scenes_dl1018.m`，SHA256 `454106AD22F44EBF5A2210FBD50A7672B5508E550EBFC80C16158E5CDBEE544A`。
- KAN14 final60k：`...\corrected_reference_training_v1\corrected_pair_training\models\official\KAN14\seed2026102001\final_step.pt`，SHA256 `BFF45DD31C288A5CEF8EE018B6EFA289419E48D1942319A5498971D02E2D4269`；MATLAB MAT SHA256 `0A24606FF8FCCC3B51503874C36063A7F2B648B36109368EA184D5BCBB8219C9`。
- DSSM14 final60k：`...\corrected_reference_training_v1\corrected_pair_training\models\official\DSSM14\seed2026102001\final_step.pt`，SHA256 `544B018B78187D9D9CBBCBD5C3332244B80AD91CB137F32BD71198A4302DFBF5`；MATLAB MAT SHA256 `6F3628B10540C617496B2A20F249C4319AF79C1A02D5945F1F91F0AEAD9C9B6E`。
- `PAIR_FINAL60K_FITS.json` SHA256 `F3C897D37F64F289038062E31D3118FB15E64D121E01954833724F29ADD54CD7`；`PAIR_FINAL60K_EXPORTS.json` SHA256 `E9A3916C81815B263355FB39240A0C9D0CB2B39FCB6343D208682A7C8CCDAA`；MATLAB parity `PAIR_MATLAB_PARITY_G6.json` SHA256 `F215890EAC4630CE855C1223434D170B5F7F8DE589D12873178D10E7F4DFC47A`，状态 `PASS_G6_MATLAB_PARITY`。两模型均对应 `final_step.pt@60000`，parity 使用 64 个固定 VAL fixtures；Plant=0、optimizer=0、TEST=0。

本仓结果入口为 [corrected14 72 场报告](../../corrected14_full72_benchmark_20261021/RESULTS_14D_VS_B_ZH.md)、`PAIR14_SCENE_RESULTS_VS_B.csv` 与 `VALIDATION_SUMMARY.json`。结果文件 SHA256 分别为 `4AF9E7C5A925C6BC0730184BEC3DC74879A4FDE2A163938B4E112E6DE8A16B75`、`B2264145E9D18896F5764FFE38302576DD08C80E7CCE1C277323246092169137`、`E3759BA831CE8DD71F41846C49F9F7068B1E93B065AFCF43C656D358A02C5BAC`。报告状态为 FINAL_COMPLETE：B 均值 Q=17.058080675 mm，corrected DSSM14=12.387217899 mm（46 胜/26 负），corrected KAN14=15.041578554 mm（28 胜/44 负）。这些是已查看的 VAL/DEV 开发验证结果，不是盲测；没有读取 TEST。

## 改动与 SHA256

工作区起始记录中保存的关键旧→新哈希：

| 文件 | 修改前 SHA256 | 当前 SHA256 |
|---|---|---|
| `matlab/scenes/make_scenes_dl1018.m` | `42C8DCF94B9BD52AB16ABE7991326DFCFCCDCDF15810BB4B19A6D7A87E67A13F` | `ED3064920AA6077384EABEB08C5FAB458314FF05AE5D35F3954C8809476B5B78` |
| `matlab/runtime/collect_position_dev_dl1018.m` | `291A0DC7780D58F5497C539CA85C0FC6BBF4B5295791B9288E96127C9693F12D` | `008AF54A359F684C1FF1144789BFBEFDBCE377212B7886001F400FFCD6C844E6` |
| `matlab/runtime/run_gate_dl1018.m` | `CCC749FE1291429FC29137BA50ADF877EA92C315609819A61C5B7CB2156CA80D` | `03317C5912A22384338CF67023C594CB2B0951B9E9A42DD2161798B923389FB6` |
| `run_dl1018.py` | `5242AD70D866B71D5D78FF567B26A051E00A93E7B4F3596E23AFFAE054EB49B7` | `EDF9B2B220EB72EC0C420AAC0EC4D0833FDB3182A9B16FCAECCE2683C40883BA` |

其余修改文件的 pre-edit baseline 为当前 HEAD blob（本轮仅有下列局部 diff）：`collect_dual_eval_dl1018.m` `7588F41E2C1A121A91DB7C964C443A1D59C5EC15E14F5989F0287544C538350E`；`collect_g02_position_teacher.m` `8BD0AB1DEA4CE00BBBF70B32BBB5283DEB57D984CA1B4005E23230413C1CC8E5`；`collect_position_role_dl1018.m` `E1AAF94878C0B17B7DE9CEDFD79CA954D680958E6CC3342BBD6AFBAD9DBC7475`。当前 SHA256：dual `52E3BE4319208EE88AB22765E5AF67F79482039B8EF2BAD18D8AD786F5EC0344`；G02 `3F484F7BDCE30ADDD8F520D10F0E316AD24F7BA2D9D2F3FE8F2ECBCAF10A9043`；role `7582F9A02458FAC6CC9822D3198020E526CC501A556887C834792F82AA31F496`；新 helper `AEBA2C9861AC7FBBA091C19DBFE1C98A6DD0F35581F9CE0F98EECA44507BA2BE`；Python test `CE45DAA9FA6CC27C0B0CF646AD5B914CF06C7A28DE09F0130DD7F74A304EDDD6`；MATLAB numeric test `7A9F74AB71F8AD2757E8DFEA3B0BF0EA9E945707254B57EF32E9EB0749CB8D0B`；MATLAB cache test `0F916BFC5C41F19D012666D084CE15E3DF92A100E670D8427F343544537ECE3D`。

未修改的历史源 `matlab/scenes/make_scenes_source_v311.m` SHA256 为 `7D1D9B2C19E098D18149ED0FF783EC17DBCE4FDAE347333580A9A7DB6BDC4E82`。除此处列出的源码、测试、README 链接与本工程说明外，没有修改历史数据、历史报告、场景快照、模型或隔离实验树；没有切分支、提交或推送。
