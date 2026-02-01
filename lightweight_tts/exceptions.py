# 最小化的异常定义，只包含 TTS 相关的异常

class TtsException(Exception):
    """TTS 基础异常"""
    pass

class InputRequired(TtsException):
    """输入参数缺失异常"""
    pass

class ModelRequired(TtsException):
    """模型参数缺失异常"""
    pass

class InvalidTask(TtsException):
    """无效任务异常"""
    pass
