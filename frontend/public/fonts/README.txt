把 emoji 字体文件放在本目录，命名为 emoji.ttf

  public/fonts/emoji.ttf

构建后会被复制到 backend/static/fonts/emoji.ttf，
前端 global.css 里的 @font-face('/fonts/emoji.ttf') 会自动加载它，
从而不依赖麒麟 V11 系统字体即可显示 emoji 图标。

推荐字体（任选其一，复制后改名为 emoji.ttf）：
  - 彩色：NotoColorEmoji.ttf （视觉更好；个别老旧 Chromium 可能不渲染彩色）
  - 单色：NotoEmoji-Regular.ttf （黑白矢量字形，任何浏览器都能渲染，最稳妥）

V11 上这两个文件通常已随 google-noto-emoji 包安装，可用：
  fc-list | grep -i emoji
找到 .ttf 路径后复制过来即可。

【免重新构建的捷径】也可直接把 emoji.ttf 放到部署目录：
  /opt/repair-system/backend/static/fonts/emoji.ttf
（@font-face 路径已固定为 /fonts/emoji.ttf，放好刷新浏览器即可）
