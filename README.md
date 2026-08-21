# Video Inspector

Windows 本地 Web 视频质检工具。应用通过 FFprobe 读取媒体信息，通过 FFmpeg 检测解码错误、黑屏、静音和冻结画面，并生成 JSON/HTML 报告。

## 运行

Web 版仅监听 `127.0.0.1`，上传的视频不会离开当前电脑。

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd web
pnpm install
pnpm run build
cd ..
.\.venv\Scripts\python.exe -m app.web.launcher
```

打包 Windows EXE：

```powershell
.\scripts\build_web.ps1
```

产物位于 `dist/VideoInspectorWeb/VideoInspectorWeb.exe`。

程序支持本地 VOD HLS 检测。在页面中选择“添加 M3U8”，通过浏览器调用的
Windows 文件夹选择器选中包含播放列表和分片的整个目录，例如：

```text
E:\新建文件夹\dist\data\outputs\001\HLS
```

程序会递归扫描文件夹中的所有媒体播放列表，将 `ep01/360P/index.m3u8` 这类
播放列表和它引用的全部 `.ts` 分片作为一次连续检测。多清晰度目录会按
`360P`、`720P`、`1080P` 分组，并为每个分集创建独立任务；`master.m3u8` 只作为
索引文件上传，不会被重复检测。检测结束后仅清理临时副本，不会修改或删除原始
`.m3u8` 和 `.ts` 文件。
当前支持已结束的 VOD 播放列表，不支持直播或加密 HLS；多清晰度主播放列表会被识别为索引并跳过，实际清晰度播放列表会继续检测。

自动化或固定端口启动时可设置 `VIDEO_INSPECTOR_PORT`；设置
`VIDEO_INSPECTOR_NO_BROWSER=1` 可禁止自动打开浏览器。

页面顶部的“退出程序”会取消未完成任务、清理临时上传文件并关闭本地服务。
浏览器关闭标签页后，如果 15 秒内没有新的心跳，程序也会自动退出；首次启动后
60 秒没有浏览器连接时同样会自动退出。普通浏览器可能禁止网页关闭非脚本创建的
标签页，此时页面会显示关闭提示和手动关闭按钮。

## 测试与打包

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\scripts\build_web.ps1
```

打包结果位于 `dist/VideoInspectorWeb/`。
