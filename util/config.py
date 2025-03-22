import os

import yaml


def replace_env_variables(value):
    """
    替换字符串中的环境变量占位符。
    支持格式：${ENV_VAR} 或 ${ENV_VAR:default_value}
    """
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        # 去掉 ${ 和 }
        env_var = value[2:-1]
        # 检查是否有默认值
        if ":" in env_var:
            var_name, default_value = env_var.split(":", 1)
            return os.getenv(var_name, default_value)
        else:
            return os.getenv(env_var, value)  # 如果环境变量不存在，返回原始值
    return value


def deep_replace_env_variables(data):
    """
    递归遍历字典或列表，替换所有环境变量占位符。
    """
    if isinstance(data, dict):
        # 如果是字典，递归处理每个键值对
        for key, value in data.items():
            data[key] = deep_replace_env_variables(value)
    elif isinstance(data, list):
        # 如果是列表，递归处理每个元素
        for i, item in enumerate(data):
            data[i] = deep_replace_env_variables(item)
    elif isinstance(data, str):
        # 如果是字符串，替换环境变量
        data = replace_env_variables(data)
    # 其他类型（如整数、布尔值）直接返回
    return data


def load_config():
    """
    加载配置文件并替换环境变量。
    """
    with open("config.yml", 'r', encoding='utf-8') as file:
        internal_config = yaml.safe_load(file)

    # 替换环境变量
    return deep_replace_env_variables(internal_config)


# 加载配置
config = load_config()