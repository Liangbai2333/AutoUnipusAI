# AutoUnipusAI
## U校园AI版自动做题工具 (Developing)
***
## 介绍
* ### 本项目主要用于英语学科的学习与参考
* ### 本项目是基于大模型语言处理开发的自动做题工具
* ### 音视频部分采用本地模型转文字处理
***
## 已知问题
- [ ] 大模型给出的答案如果比题目少, 这时点提交会发生未作答完成, 导致程序错误  
- [ ] 提交后如果分数不达标, 并且出现继续学习按钮, 会跳转到下一个Tab而不是重试
- [ ] 多选题再按一次会取消选择, 导致未作答完成
- [ ] 还有一些题目类型不支持

### 上述问题可能会在我下次需要写英语作业的时候解决 (bushi
***
## 使用方式

### 1. 安装Python环境
前往官网安装: **https://www.python.org/downloads**

或者直接安装Conda

**请将其配置到环境变量中**

### 2. 安装ffmpeg依赖
前往官网安装: **https://ffmpeg.org/download.html **
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
### 5. 配置虚拟环境，安装必要的依赖

1. 在AutoUnipusAI目录下打开终端(windows/macOS)或cmd(windows)
2. 输入命令 python -m venv .venv
3. 激活虚拟环境 
   * windows: .venv/Scripts/activate
   * macOS: source .venv/bin/activate
4. 安装依赖 pip install -r requirements.txt
5. 执行python main.py

## 注意事项
* ### 若显卡支持CUDA, 请配置完CUDA再使用, 可加速音视频转文字的计算速度 (默认使用CPU计算)
* ### 禁止用于商业用途 (代刷等)
* ### 本项目只能用于学习使用
# 本项目仅供学习使用！！！