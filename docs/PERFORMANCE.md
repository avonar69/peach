# 实验性能选项

「浏览与播放」提供两个独立实验开关，默认关闭，保存在当前浏览器。视频开关用于下一次打开的影片；界面开关控制后续浏览查询。

## 视频载入与跳转

「Faster video loading and seeking (Beta)」为本地、非计费影片增加 `preload=auto` 提示，并在普通 `/stream` 响应上允许五分钟的私有浏览器缓存。Range、ETag、鉴权、流会话取消及格式转换判据继续适用。远端来源、STRM 代理、修复头与 HLS 使用各自既有响应策略；媒体原文件不被改写。浏览器决定实际预载量，开启后可能增加内存和局域网流量。

Peach 的普通文件响应已经支持字节 Range、1 MiB 读取与断开取消。浏览器跳转还受容器索引位置、关键帧间隔、解码支持和需要的转换影响；SMB 加桌面播放器的读取及解码路径不同，因此不能仅凭局域网连接保证两者相同。

研究采用以下一手资料：

- [MDN：HTTP Range 请求](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Range_requests)说明按字节取回媒体范围，是随机访问的基础。
- [MDN：preload](https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement/preload)将自动预载定义为浏览器提示，不能保证缓存完整影片。
- [MDN：fastSeek](https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement/fastSeek)明确存在精度取舍且兼容性有限。四向快捷键继续使用精确 `currentTime`，不以近似关键帧跳转替代设置的秒数。
- [FFmpeg：MOV/MP4 faststart](https://www.ffmpeg.org/ffmpeg-formats.html#Options-9)介绍移动索引以利于起播。该操作需要生成媒体文件；实验开关不自动重封装馆藏，已有修复与转换能力保持独立。

## 界面切换

「Faster section navigation (Beta)」复用共享 TanStack Query 缓存里的统计、口味、人物名册、实体资料及照片快照，最长三十秒。写操作主动失效仍生效；任务、配置、复核及下载状态不使用这段实验缓存。首次访问与缓存过期仍需请求服务端，不能消除服务器慢查询本身。

实现复用已固定的 TanStack Query 5.104.3，不增加依赖。[官方预取指南](https://tanstack.com/query/latest/docs/framework/react/guides/prefetching)与[默认缓存行为](https://tanstack.com/query/latest/docs/framework/react/guides/important-defaults)说明 `staleTime` 对请求复用的控制；没有将手写路由缓存替代共享客户端。

## 音量与键盘

带控件的播放器保存音量和静音状态，在同一浏览器、同一网站地址的下一部影片恢复。无控件预览的自动静音不写入此偏好。更换设备、浏览器或网站地址不共享该本机设置。

播放器在控件处理按键前应用用户的四向跳转设置，避免焦点落在时间滑条时使用控件自身的步长。音量滑条、菜单与编辑框保留自己的键盘行为，关闭播放器时解除监听。

## 验证范围

时间轴缩略图采集是独立后台任务。任务浮层与数据管理页显示影片与当前抽帧进度，提供停止入口；自动启动的采集也会被发现，停止保留已完成的图片。任务完成、停止或失败时，两处运行面板自动隐藏。

缩略图速度独立保存，复用扫描的三档控制。低占用是默认档，FFmpeg 解码、过滤和编码各用一个线程，相邻抽帧至少间隔 0.75 秒；标准档各用两个线程，相邻抽帧至少间隔 0.2 秒；全速交给 FFmpeg 默认线程调度，不加抽帧间隔。运行期间可切档，新的预算从下次抽帧生效；10 秒或 30 秒采样密度独立于处理速度，不改变图片质量和时间轴位置。扫描的速度偏好不影响独立缩略图采集。停止会终止并回收该任务自己启动的 FFmpeg 子进程。

播放器按单格尺寸裁切时间轴图，包括末张不足十行的图片；缩略图不受页面通用图片最大宽度约束。桌面与手机回归覆盖新播放、恢复播放及索引延迟到达时的后备图片。

临时媒体与模拟响应覆盖 Range、鉴权、默认关闭、浏览查询复用与写入失效、音量恢复、控件焦点下的配置步长和本地预载范围。真实馆藏、局域网吞吐、GPU 解码和 SMB 对照的计时证据未取得；这些实验开关需要使用者在实际部署中比较。
