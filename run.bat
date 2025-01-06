@echo off
REM 检查虚拟环境是否存在
if not exist ".venv\Scripts\python.exe" (
    echo 虚拟环境不存在，正在创建...
    python -m venv .venv
    echo 虚拟环境创建完成。
)

REM 激活虚拟环境
call .venv\Scripts\activate

REM 检查并安装依赖
if exist "requirements.txt" (
    echo 正在安装依赖...
    pip install -r requirements.txt
    echo 依赖安装完成。
) else (
    echo requirements.txt 文件不存在，跳过依赖安装。
)

REM 运行主程序
echo 正在运行主程序...
python main.py

REM 保持终端窗口打开（可选）
pause