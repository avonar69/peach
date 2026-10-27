# 按需拖动预览取证

核对日期：2026-10-27。本文是人工取证笔记，不登记为可覆盖的上游快照。

- **实测（公开页面）**：[用户提供的组织页](https://github.com/PotPlayer-Media-Decoder)仅列出一个 `.github` 公开仓库，内容为产品说明。解码器实现、许可与可固定的实现版本：未取得。
- **用户描述**：PotPlayer 在时间条悬停时显示画面，不要求先生成整部影片的时间轴图。此行为的本机复现、内部缓存策略与 GPU／CPU 耗时：未取得。
- **推断**：这类交互可通过按需定位并解码目标附近的画面实现，不意味着无需解码或无需读取媒体。Peach 不以该推断宣称复用了 PotPlayer 的代码。

Peach 复用浏览器标准接口：用独立的静音 `HTMLVideoElement` 定位，等待 [`seeked`](https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement/seeked_event)，通过 [`drawImage`](https://developer.mozilla.org/en-US/docs/Web/API/CanvasRenderingContext2D/drawImage)捕获解码帧。CPU／GPU 由播放设备的浏览器与驱动选择，不强制服务器 CUDA。

Peach 的差异：默认关闭的实验选项；只为非计费本地影片取帧；140 毫秒防抖、一个解码器、最多二十帧内存缓存。离开时间条或销毁播放器即取消该预览会话；不写时间轴文件，不启动服务器采集或转换。不兼容片源保留已保存时间轴或时间提示，不能以网页播放器假装拥有桌面播放器的全部解码能力。

验证使用临时合成媒体与浏览器夹具，生产 GPU、Firefox／Safari 的实际 HEVC 解码及 PotPlayer 对照性能均未取得。
