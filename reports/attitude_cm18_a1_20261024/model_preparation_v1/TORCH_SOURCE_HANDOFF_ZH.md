# CM18-A1 Torch 源码交接

按 root 新任务只新增可训练模块与一致性检查源码；没有运行 optimizer、GPU、MATLAB 或 Plant，也没有读取数据缓存。NumPy inference reference（`model_cm18_v1.py` SHA256 `ad32c4f97bf96c63172547c944d80c45062502f1062b774934e0f7a868720cf6`）保持未改。

Torch 模块 `experiments/attitude_cm18_a1_20261024/torch_model_cm18_v1.py` SHA256 `bc9fe34fe957cb624438eeccfdfe2ddd38ad40cc9a4e706ce58863c9271d5aa0`，实现相同的 `18→32 tanh→32 tanh→24 linear` 和 `A(x) @ [z/2;u]` 结构。nn.Linear 的权重布局与 NumPy `W[out,in]` 一致，24 个末层 bias 作为系数 bias 保留；模型总计 2,456 个 trainable parameters，归一化器和 TRAIN 三轴 RMS 是 buffers，不计入参数。默认 double CPU 便于逐元素 parity；之后可按正式训练任务书转为指定设备/dtype。

`check_cm18_torch_parity_v1.py` SHA256 `4e43e080a454a0a580a74883e6297d343af95efe071461d2b3c85135bfaed008` 是合成fixture检查源码，不加载 cache。它计划检查 NumPy 参数逐元素装载、NumPy/Torch单样本与batch前向、严格零基输出、输入有限差分梯度，以及末层系数bias的解析梯度。源码会生成/使用 CPU 检查结果，optimizer steps 固定为 0。检查未运行。

已与负责数据导出的 peer 确认缓存接口；当前仍是准备中的接口，不能视作已经生成的数据。屏幕四例目录为 `reports/attitude_cm18_a1_20261024/data_preparation_v1/events_screen4_v1/`，全量目录为 `.../events_all816_v1/`。每场 MAT 平铺变量使用 `X18` double `[1999,18]`、`target_raw` double `[1999,3]`、`event_time_s`、`phase_code`、`plant_index`、char `scene_id/split`、`input_identity` 和 `export_meta`。逐行对应同一事件；`plant_index` 为 MATLAB 1 基 `[11,21,...,19991]`。`X18` 列顺序与模型输入相同，标签保持 rad/s² 原尺度。screen4 与 all816 分别使用 `DATASET_MANIFEST_v1.json`，all816 清单会引用已审过的四个 screen4 文件，不复制覆盖。未来训练/目标 scale 仅从 TRAIN 数据派生，VAL 不参与归一化。此交接没有实现缓存读取器，peer 的导出文件保持独立。

取得 fixture 并进行后续本地检查的命令如下；本次没有执行：

```powershell
python .\experiments\attitude_cm18_a1_20261024\model_cm18_v1.py --export-parity-fixture .\experiments\attitude_cm18_a1_20261024\parity_fixture_v1.json
python .\experiments\attitude_cm18_a1_20261024\check_cm18_torch_parity_v1.py --fixture .\experiments\attitude_cm18_a1_20261024\parity_fixture_v1.json
```

正式训练尚未获准；初始化 seed、optimizer、loss、数据清单身份和开发集评估协议都待单独冻结。本次源码不是训练或闭环结果，也没有改动既有 C5、NumPy inference、peer 数据导出文件或 TEST。
