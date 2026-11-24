批量照片水印工具 v1.2
一个给照片批量添加左下角水印的小工具，提供 Windows 图形界面和命令行两种用法。原图不会被修改，输出文件夹不存在时会自动创建。
直接使用 Windows 版（推荐）
解压 `照片水印工具\_v1.2\_win64.zip`。
保持解压后的文件夹完整，双击里面的 `照片水印工具.exe`。
按界面提示选择照片文件夹、水印图片和输出文件夹，点击“开始处理”。
不需要安装 Python。请勿只把 `照片水印工具.exe` 单独复制出来，它需要同目录下的 `\_internal` 文件夹才能运行。
如果 Windows 首次运行时提示“Windows 已保护你的电脑”，这是因为程序没有数字签名：
点击提示框里的“更多信息”。
点击“仍要运行”。
界面功能
选择照片文件夹后，会自动填入默认输出位置。
输出文件夹可以自己指定；不存在时会自动创建，包括多级目录。
可调整水印宽度、边距、不透明度、JPEG 质量。
可选择是否处理子文件夹、是否跳过已经存在的成品。
处理过程中会显示进度和日志；完成后可以直接打开输出文件夹。
源码运行
环境要求：
Python 3.10 或更高版本
Pillow
安装依赖：
```powershell
cd D:\\DeepseekHarness\\photo-watermarker
python -m pip install -r requirements.txt
```
启动图形界面：
```powershell
python watermark\_gui.py
```
命令行用法
```powershell
python watermark\_photos.py "D:\\我的照片" "D:\\素材\\logo.png"
```
默认输出到输入文件夹同级：
```text
D:\\我的照片\_watermarked
```
原图不会被修改。也可以指定输出文件夹：
```powershell
python watermark\_photos.py "D:\\我的照片" "D:\\素材\\logo.png" -o "D:\\成片"
```
常用示例：
```powershell
# 递归处理所有子文件夹，并保持目录结构
python watermark\_photos.py "D:\\我的照片" "D:\\素材\\logo.png" -r

# 调小、调淡水印，指定输出文件夹
python watermark\_photos.py "D:\\我的照片" "D:\\素材\\logo.png" `
  -o "D:\\成片" --scale 0.15 --opacity 0.8

# 中断后继续处理，跳过已经存在的成品
python watermark\_photos.py "D:\\我的照片" "D:\\素材\\logo.png" -r --skip-existing
```
参数说明
参数	默认值	作用
`input\_folder`	必填	照片所在的文件夹
`watermark`	必填	水印图片的完整路径，推荐透明背景 PNG
`-o, --output`	同级 `<文件夹名>\_watermarked`	自定义输出文件夹；不存在会自动创建
`-r, --recursive`	关闭	递归处理子文件夹，并保持原目录结构
`--scale`	`0.20`	水印宽度占照片宽度的比例
`--margin`	`0.03`	水印距左边和下边的距离，占照片短边的比例
`--opacity`	`1.0`	水印不透明度，范围 `(0, 1]`
`--quality`	`95`	JPEG/WebP 输出质量，范围 `1-100`
`--skip-existing`	关闭	输出文件已存在时跳过
`-v, --verbose`	关闭	出错时打印完整错误堆栈
`--version`	-	显示版本
默认效果：水印宽度为照片宽度的 20%，左下角留出约为照片短边 3% 的空白。
支持的照片格式
JPG/JPEG/JFIF、PNG、WebP、BMP、TIF/TIFF。
HEIC/HEIF（部分 iPhone 照片）默认未支持，请先转换为 JPG 或 PNG。GIF 动图也不处理。
处理规则
默认只处理照片文件夹本层的图片；加 `-r` 才处理子文件夹。
水印按比例缩放，如果水印太高，会自动缩小到照片范围内。
水印固定在照片左下角，距左边和下边各留出边距。
输出文件夹可自定义；不存在时会自动创建，已存在时直接写入。
输出目录中的同名文件默认会被覆盖；原图始终不动。输出目录不能和原图目录相同。
水印文件本身位于照片文件夹中时，会自动跳过，避免把水印当成照片处理。
输出文件夹位于照片文件夹内部时，`-r` 模式会自动忽略该输出文件夹，不会重复处理成品。
JPEG 是有损格式，即使质量设为 95 也会重新编码一次；原图不会被改动。
常见 JPEG/PNG/WebP 照片会保留 EXIF 和 ICC 信息；EXIF 方向会先转正再定位水印。
退出码
命令行模式：
`0`：全部成功（或有文件被跳过）。
`1`：有照片处理失败，其余照片仍会继续处理。
`2`：参数或路径错误，例如文件夹不存在、找不到水印、没有可处理的照片。
`130`：用户按下了 `Ctrl+C`。
重新打包 Windows 版
安装打包依赖：
```powershell
python -m pip install -r requirements-build.txt
```
执行：
```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\build\_exe.ps1
```
会生成：
`dist\\照片水印工具\\照片水印工具.exe`
`照片水印工具\_v1.2\_win64.zip`
说明：PyInstaller 单文件版在本机启动时无法创建临时解包目录，因此这里采用免安装的 `onedir`（绿色文件夹）方式打包，功能相同。exe 必须和 `\_internal` 文件夹放在一起，不能只单独复制 exe。
