"""
AI助手的工具函数集合
"""
import datetime
import json
import random
from typing import Annotated
import requests
import math

def get_current_time() -> str:
    """获取当前日期时间"""
    now = datetime.datetime.now()
    # 中文星期映射
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday_name = weekdays[now.weekday()]
    return f"现在是{now.strftime('%Y年%m月%d日 %H:%M:%S')} {weekday_name}"

def calculate(expression: Annotated[str, "数学表达式，如 '2+2', 'sqrt(16)', 'sin(3.14159/2)'"]) -> str:
    """计算数学表达式"""
    try:
        # 安全的数学函数白名单
        safe_dict = {
            'abs': abs, 'round': round, 'pow': pow,
            'sqrt': math.sqrt, 'sin': math.sin, 'cos': math.cos,
            'tan': math.tan, 'log': math.log, 'exp': math.exp,
            'pi': math.pi, 'e': math.e
        }
        
        # 计算表达式
        result = eval(expression, {"__builtins__": {}}, safe_dict)
        return f"计算结果：{expression} = {result}"
    except Exception as e:
        return f"计算错误：{str(e)}"


def get_weather(city: Annotated[str, "城市名称，如北京、上海"]) -> str:
    """获取天气信息（模拟数据）"""
    # 这里使用模拟数据，实际应用中应该调用真实的天气API
    weather_conditions = ["晴", "多云", "阴", "小雨", "中雨", "大雨", "雪"]
    temp = random.randint(-10, 35)
    condition = random.choice(weather_conditions)
    humidity = random.randint(30, 90)
    wind_speed = random.randint(0, 30)
    
    return f"{city}天气：{condition}，温度 {temp}°C，湿度 {humidity}%，风速 {wind_speed}km/h"






