# 去水印平台开发计划

## 一、开发目标

1. 建立稳定可复现的评测基线。
2. 提升固定角标 / 小面积平台水印场景的成功率。
3. 增加参数分档、workflow 分流和基础后处理。
4. 为后续复杂场景优化预留扩展点。

## 二、阶段计划

### P0：基线和可观测性

开发任务：

1. 建立评测集目录：
   - `plans/eval_dataset/simple`
   - `plans/eval_dataset/medium`
   - `plans/eval_dataset/hard`
2. 为每次运行记录元数据：
   - workflow 文件名
   - quality profile
   - steps
   - subvideo_length
   - neighbor_length
   - mask_dilation_iter
   - device
   - seed
3. 固定当前 `workflows/sam2_diffueraser_api.json` 为基线 workflow。
4. 新增平行 workflow 文件，不直接覆盖基线：
   - `workflows/sam2_diffueraser_balanced.json`
   - `workflows/sam2_diffueraser_quality.json`

涉及文件：

- `src/wm_platform/provider_runtime.py`
- `src/wm_platform/repository.py`
- `workflows/sam2_diffueraser_api.json`
- `workflows/sam2_diffueraser_balanced.json`
- `workflows/sam2_diffueraser_quality.json`

交付标准：

- 能跑通评测集。
- 能输出每个 case 的参数记录。
- 能对比不同 workflow 的输出差异。

### P1：角标场景优先和 mask 稳定性

开发任务：

1. 在运行时增加简单场景判定：
   - 是否位于四角
   - 面积是否较小
   - 多帧位置是否稳定
2. 满足条件时切换到专用 workflow：
   - `workflows/corner_watermark_hq.json`
3. 增加 mask 时序平滑：
   - 面积变化阈值限制
   - 中心点漂移阈值限制
   - 小面积离散区域过滤
4. 增加 mask 合法性检查：
   - 区域面积过大
   - 多个分散区域
   - 跨帧跳动过大
5. 对低置信度 case 做保守处理或失败分流。

涉及文件：

- `src/wm_platform/provider_runtime.py`
- `workflows/corner_watermark_hq.json`
- `tests/test_api_workflow.py`

交付标准：

- 简单固定角标场景成功率提升。
- 误擦主体内容的 case 减少。
- 闪烁和边缘跳动下降。

### P1.5：参数分档

开发任务：

1. 增加配置项：

```env
DWM_QUALITY_MODE=fast|balanced|quality
```

2. 在运行时按档位加载不同 workflow 或参数。
3. 建议默认参数：

| 档位 | steps | subvideo_length | neighbor_length |
|------|-------|-----------------|-----------------|
| fast | 2-4 | 50 | 10 |
| balanced | 4-6 | 60-80 | 12-16 |
| quality | 6-8 | 80-120 | 16-24 |

4. 参数调优顺序：
   - `steps`
   - `mask_dilation_iter`
   - `subvideo_length`
   - `neighbor_length`
   - `ref_stride`

涉及文件：

- `src/wm_platform/config.py`
- `src/wm_platform/provider_runtime.py`
- `tests/test_api_workflow.py`

交付标准：

- 支持质量档位切换。
- 能稳定选择对应 workflow / 参数组合。

### P2：基础后处理

开发任务：

1. 增加修补区域和原视频的轻量混合。
2. 增加边缘 feather。
3. 增加局部锐化开关。
4. 增加基础闪烁抑制或失败帧平滑兜底。

涉及文件：

- `workflows/sam2_diffueraser_balanced.json`
- `workflows/sam2_diffueraser_quality.json`
- `workflows/corner_watermark_hq.json`
- `src/wm_platform/provider_runtime.py`

交付标准：

- 输出边缘更自然。
- 修补区域的观感改善。

## 三、文件级任务清单

### `src/wm_platform/provider_runtime.py`

1. 增加 workflow 选择逻辑。
2. 增加 quality profile 注入逻辑。
3. 增加运行元数据记录。
4. 增加低置信度 case 分流逻辑。
5. 增加角标场景规则判断入口。

### `src/wm_platform/config.py`

1. 增加 `DWM_QUALITY_MODE` 配置。
2. 预留 quality 相关参数配置项。

### `src/wm_platform/repository.py`

1. 增加运行元数据落库支持。
2. 预留 workflow / quality profile 查询能力。

### `workflows/`

1. 保留 `sam2_diffueraser_api.json` 作为基线。
2. 新增：
   - `sam2_diffueraser_balanced.json`
   - `sam2_diffueraser_quality.json`
   - `corner_watermark_hq.json`

### `tests/test_api_workflow.py`

1. 增加 quality profile 测试。
2. 增加 workflow 选择测试。
3. 增加低置信度 case 分流测试。

## 四、排期

### 第 1 周

1. 建评测集目录。
2. 增加运行留痕。
3. 拆出 `balanced` 和 `quality` workflow。
4. 跑第一轮基线。

### 第 2-3 周

1. 做角标优先规则。
2. 做 mask 时序平滑。
3. 做 mask 合法性检查。
4. 补测试。

### 第 4 周

1. 增加质量档位切换。
2. 增加基础后处理。
3. 锁定默认生产参数。

## 五、验收标准

### P0 验收

- 能跑通评测集。
- 能记录每次运行参数。

### P1 验收

- 固定角标场景成功率明显提升。
- 明显误擦 case 下降。

### P1.5 验收

- 支持 `fast / balanced / quality` 三档切换。
- 档位切换后输出和参数记录一致。

### P2 验收

- 输出边缘更自然。
- 局部闪烁减少。
