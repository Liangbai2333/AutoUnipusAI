# AutoUnipusAI
## U校园AI版自动做题工具 (Developing)
***
## 介绍
* ### 本项目主要用于英语学科的学习与参考
* ### 本项目是基于大模型语言处理开发的自动做题工具
* ### 音视频部分采用本地模型转文字处理
***
## 使用方式

### 1. 安装Python环境
前往官网安装: **https://www.python.org/downloads/windows/**
### 2. (可选) 安装ffmpeg依赖
前往官网安装: **https://ffmpeg.org/download.html#build-windows**  
若未安装, 程序将自动下载到本地工作目录
### 3. 申请一个支持工具调用的大模型的API-KEY
你可以直接申请Deepseek的API-KEY: **https://www.deepseek.com/**
### 4. 配置config.yml中的配置项
```yaml
ai:
  model: "deepseek-chat"
  openai_api_key: 在这里输入你的apikey
  openai_api_base: "https://api.deepseek.com/v1" # 这里是deepseek的api链接

unipus:
  username: 输入U校园账号
  password: 输入U校园密码
  book: "20000057510"
  offset: 5
  page_wait: 5
  tab_wait: 3
  task_wait: 3
  video_sleep: 5
```
### 5. 自行构建Python虚拟环境或直接运行目录中的 run.bat

## 注意事项
* ### 若显卡支持CUDA, 请配置完CUDA再使用, 可加速音视频转文字的计算速度 (默认使用CPU计算)
* ### 禁止用于商业用途 (代刷等)
* ### 本项目只能用于学习使用
# 本项目仅供学习使用！！！