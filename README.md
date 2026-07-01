# MarkitdownPlus
基于Markitdown进行一些易用性改进。

主要变更：
使用MinerU的Excel解析代替原始的pandas.read_excel
输出表格从MinerU的html格式转换为markdown格式，保留原始表格中的各种格式。
通过Hook修改Markitdown的OCR功能，使其支持图片文件导出、Caption、OCR等多种可选功能。

## 使用说明

### 启动 FastAPI 服务
```bash
python fast_api_v2.py
# 或
uvicorn fast_api_v2:app --host 0.0.0.0 --port 8000
```

### 启动 WebUI
```bash
python markitdown_webui_v2.py
```
