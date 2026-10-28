# Torch CPU 检查的环境记录

本记录补存前一工作段已观察到的结果，不代表重新执行或新增训练。现存 ROOT_TORCH_PARITY_RESULT_v1.json 是三组合成参数检查的真实输出，先前命令已观察到 OS exit 0；梯度检查只做自动微分/有限差分，没有 optimizer step 或 Plant。

首次失败见 ROOT_TORCH_CHECK_ATTEMPT01_v1.json：手工转写源码 SHA 错误，hash gate 在模型测试前终止，exit 1。之后修正 SHA 的命令遇到 `OMP Error #15: Initializing libiomp5md.dll, but found already initialized`，exit 1，未完成 parity，未启动训练。没有保留下该次独立 stdout 文件，本记录不冒充原始进程日志。

使用以下进程局部环境后，同一三组 parity 检查通过，物理输出最大差 1.7763568394002505e-15，梯度检查通过；没有安装包或全局环境修改，没有删除 DLL：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:OMP_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:MKL_THREADING_LAYER='SEQUENTIAL'
```

不得通过 `KMP_DUPLICATE_LIB_OK` 绕过重复数学运行库检查。Intel 对环境变量的官方说明见 [oneMKL threading layer](https://www.intel.com/content/www/us/en/docs/onemkl/developer-guide-windows/2023-1/dynamic-select-the-interface-and-threading-layer.html)。这里仅证明当前 CPU 合成模型检查可运行，正式 CUDA 训练环境仍需启动前检查和实际记录。
