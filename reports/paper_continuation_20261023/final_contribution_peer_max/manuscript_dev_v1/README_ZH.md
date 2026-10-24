# manuscript_dev_v1

这是C5的英文限定范围LaTeX短稿初稿，附已核引文和中文证据映射。内容仅使用开发集；TEST48尚未执行，不含独立测试数值。稿件明确区分预训练物理标签与在线PCF坐标标签，并将冻结W0解释为保留网络的冻结权重消融。

主文件为`main.tex`，参考文献为`references.bib`。中文证据、数值来源、理论适用范围和文献访问限制见`EVIDENCE_MAP_ZH.md`。

在本机已安装的MiKTeX环境中，本稿使用下列命令完成编译与交叉引用：

```powershell
pdflatex -interaction=nonstopmode -halt-on-error main.tex
bibtex main
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

本机latexmk入口因缺少Perl而不可用；直接调用pdflatex与bibtex已通过。输出PDF只用于编译检查，短稿仍需作者审核并在TEST及剩余文献核查完成后更新。
