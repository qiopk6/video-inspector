# Video Inspector

Windows 本地视频质检工具。应用通过 FFprobe 读取媒体信息，通过 FFmpeg 检测解码错误、黑屏、静音和冻结画面，并生成 JSON/HTML 报告。项目同时提供浏览器界面和 PySide6 桌面界面。

## Web 版运行

Web 版仅监听 `127.0.0.1`，上传的视频不会离开当前电脑。

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-web.txt
cd web
pnpm install
pnpm run build
cd ..
.\.venv\Scripts\python.exe -m app.web.launcher
```

打包 Web 版：

```powershell
.\scripts\build_web.ps1
```

产物位于 `dist/VideoInspectorWeb/VideoInspectorWeb.exe`。

Web 版支持本地 VOD HLS 检测。在页面中选择“添加 M3U8”，通过浏览器调用的
Windows 文件夹选择器选中包含播放列表和分片的整个目录，例如：

```text
E:\新建文件夹\dist\data\outputs\001\HLS\ep001\1080P
```

程序会把文件夹上传到本机临时目录，将其中的播放列表作为一次连续检测读取；
检测结束后仅清理临时副本，不会修改或删除原始 `.m3u8` 和 `.ts` 文件。
当前支持已结束的 VOD 播放列表，不支持直播、加密 HLS 和多清晰度主播放列表。

自动化或固定端口启动时可设置 `VIDEO_INSPECTOR_PORT`；设置
`VIDEO_INSPECTOR_NO_BROWSER=1` 可禁止自动打开浏览器。

## 桌面版运行

1. 准备 Windows 版 `ffmpeg.exe` 和 `ffprobe.exe`，放入 `tools/ffmpeg/`。
2. 创建虚拟环境并安装依赖：

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

3. 启动：

   ```powershell
   .\.venv\Scripts\python.exe -m app.main
   ```

也可以设置 `VIDEO_INSPECTOR_FFMPEG_DIR` 指向包含 FFmpeg 二进制文件的目录。

## 测试与打包

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\scripts\build.ps1
```

打包结果位于 `dist/VideoInspector/`。
