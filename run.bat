@echo off
REM ������⻷���Ƿ����
if not exist ".venv\Scripts\python.exe" (
    echo ���⻷�������ڣ����ڴ���...
    python -m venv .venv
    echo ���⻷��������ɡ�
)

REM �������⻷��
call .venv\Scripts\activate

REM ��鲢��װ����
if exist "requirements.txt" (
    echo ���ڰ�װ����...
    pip install -r requirements.txt
    echo ������װ��ɡ�
) else (
    echo requirements.txt �ļ������ڣ�����������װ��
)

REM ����������
echo ��������������...
python main.py

REM �����ն˴��ڴ򿪣���ѡ��
pause