# 评测集说明

## 目录结构

```
eval_dataset/
├── simple/    # 简单场景
├── medium/    # 中等场景
└── hard/      # 复杂场景
```

## 场景分类

### simple（简单场景）

适用于以下情况：
- 固定角标水印（位于画面四角）
- 小面积水印（< 5% 画面面积）
- 位置稳定的水印（多帧间位置变化小）

### medium（中等场景）

适用于以下情况：
- 移动水印（位置有变化但不剧烈）
- 中等面积水印（5%-15% 画面面积）
- 半透明水印

### hard（复杂场景）

适用于以下情况：
- 大面积水印（> 15% 画面面积）
- 动态水印（位置变化剧烈）
- 多个水印同时存在
- 水印与主体内容重叠

## 使用方法

1. 将测试视频放入对应场景目录
2. 运行评测脚本：
   ```bash
   python -m pytest tests/test_api_workflow.py -v -k "eval"
   ```
3. 查看输出结果和参数记录

## 记录结果

每次运行后，运行参数会自动记录到数据库中。可通过以下方式查询：

```python
from wm_platform.repository import JobRepository
from wm_platform.config import load_settings

settings = load_settings()
repo = JobRepository(settings)
metadata = repo.get_run_metadata(job_id="your_job_id")
```
