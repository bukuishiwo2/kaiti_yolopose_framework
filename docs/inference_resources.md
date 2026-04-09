# Inference Resources (Pose + Fall)

下面的资源按“上手成本”排序，优先给你用于推理验证而不是训练。

## A. 快速上手（几分钟内可跑）

| 资源 | 适用场景 | 获取方式 | 备注 |
|---|---|---|---|
| MMPose demo mp4（多人/运动） | 验证姿态与多人检测链路 | `bash scripts/download_demo_videos.sh` | URL 来自 MMPose 官方 Demo 文档示例 |
| 你已有本地短视频 | 回归测试 | 直接 `--source /path/to/video.mp4` | 最快，适合改参数后快速复验 |

## B. 多人密集场景（检验误检与稳定性）

| 资源 | 适用场景 | 获取方式 | 备注 |
|---|---|---|---|
| MOT17 | 多人、遮挡、运动相机 | 官方页面下载训练集序列 | 对“多人+遮挡”推理非常有效 |

建议先用 MOT17 里的 1~2 条训练序列做推理压测，再调 `conf/vid_stride/stabilizer`。

## C. 摔倒事件场景（检验 fall_detector）

| 资源 | 适用场景 | 获取方式 | 备注 |
|---|---|---|---|
| UR Fall Detection Dataset | 明确摔倒/ADL对照，RGB/Depth+加速度 | 官方页面逐序列下载 zip | 70 段序列（30 fall + 40 ADL），适合规则法阈值调优 |
| FALL-UP (HAR-UP) | 多活动+摔倒，多模态 | 官方页面 Download/Complete Downloads | 含相机相关数据包，适合做补充验证 |
| FallVision (Harvard Dataverse) | 近年公开摔倒视频数据 | Dataverse DOI 页面 | 页面需浏览器 JS 验证，建议手动下载 |

## D. 大规模动作视频（泛化验证）

| 资源 | 适用场景 | 获取方式 | 备注 |
|---|---|---|---|
| UCF101 | 通用动作视频覆盖面广 | UCF 官方页面下载 | 可从含人物动作类中抽样做姿态泛化测试 |

## 推荐测试顺序

1. MMPose demo 视频：先确认 pipeline 稳定输出。
2. 你的业务视频（单人/短片）：调基本阈值。
3. MOT17：调多人遮挡下误检率。
4. UR Fall：调 `fall_detector.*` 阈值与时序稳定参数。

## 资源链接

- MMPose Demo 文档: https://mmpose.readthedocs.io/en/0.x/demo.html
- MOT17: https://motchallenge.net/data/MOT17/
- UR Fall Detection Dataset: https://fenix.ur.edu.pl/~mkepski/ds/uf.html
- FALL-UP (HAR-UP): https://sites.google.com/up.edu.mx/har-up/
- FallVision Dataverse DOI: https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/75QPKK
- UCF101 官方页: https://www.crcv.ucf.edu/research/data-sets/ucf101/
